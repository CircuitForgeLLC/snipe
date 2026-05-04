# app/tasks/monitor.py
"""Background saved-search monitor — polls eBay and writes WatchAlerts for new listings.

Design notes:
- Runs synchronously inside an asyncio.to_thread() call from the polling loop.
- Uses the same eBay adapter + trust scoring pipeline as the live search endpoint.
- Dedup via watch_alerts (saved_search_id, platform_listing_id) UNIQUE constraint.
- Never takes any transactional action — alert only.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.db.models import SavedSearch, WatchAlert
from app.db.store import Store

log = logging.getLogger(__name__)


_AUCTION_ALERT_WINDOW_HOURS = 24  # alert on auctions ending within this window


def should_alert(
    *,
    trust_score: int,
    score_is_partial: bool,
    price: float,
    buying_format: str,
    min_trust_score: int,
    ends_at: "str | None" = None,
) -> bool:
    """Return True if a listing qualifies for a watch alert.

    BIN (fixed_price / best_offer): alert immediately — these sell on a first-come
    basis, so speed matters. Require a higher trust bar on partial scores to reduce
    false positives while BTF scraping is still in flight.

    Auction: only alert when the auction is within _AUCTION_ALERT_WINDOW_HOURS of
    ending. Alerting on a 7-day auction 6 days early is noise — the user can't act
    usefully until the end window anyway. Bid scheduling (paid+) and sniping algo
    (premium) are separate features built on top of this alert layer.
    """
    from datetime import datetime, timezone

    # Partial scores: apply a +10 buffer so we don't surface unreliable signals.
    effective_min = min_trust_score + 10 if score_is_partial else min_trust_score
    if trust_score < effective_min:
        return False

    if buying_format in ("fixed_price", "best_offer"):
        # BIN: alert immediately — inventory can disappear any time.
        return True

    if buying_format == "auction":
        if not ends_at:
            # No end time recorded — alert anyway rather than silently skip.
            return True
        try:
            end = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
            hours_remaining = (end - datetime.now(timezone.utc)).total_seconds() / 3600
            return 0 < hours_remaining <= _AUCTION_ALERT_WINDOW_HOURS
        except (ValueError, TypeError):
            log.debug("should_alert: could not parse ends_at=%r, alerting anyway", ends_at)
            return True

    # Unknown format — alert and let the user decide.
    return True


def run_monitor_search(
    search: SavedSearch,
    *,
    user_db: Path,
    shared_db: Path,
) -> int:
    """Execute one background monitor run for a saved search.

    Fetches current listings, scores them, writes new high-trust finds
    to watch_alerts.  Returns the count of new alerts written.

    Called from the async polling loop via asyncio.to_thread().
    """
    from app.platforms.ebay.adapter import EbayAdapter
    from app.trust import TrustScorer

    log.info("Monitor: checking saved search %d (%r)", search.id, search.name)

    filters = json.loads(search.filters_json or "{}")
    query = filters.pop("query_raw", search.query)

    try:
        adapter = EbayAdapter()
        raw_listings = adapter.search(query, **filters)
    except Exception as exc:
        log.warning("Monitor: eBay search failed for search %d: %s", search.id, exc)
        return 0

    shared_store = Store(shared_db)
    user_store = Store(user_db)
    scorer = TrustScorer(shared_store)

    try:
        trust_scores = scorer.score_batch(raw_listings, query)
    except Exception as exc:
        log.warning("Monitor: trust scoring failed for search %d: %s", search.id, exc)
        return 0

    new_alert_count = 0
    for listing, trust in zip(raw_listings, trust_scores):
        qualifies = should_alert(
            trust_score=trust.composite_score,
            score_is_partial=trust.score_is_partial,
            price=listing.price,
            buying_format=listing.buying_format,
            min_trust_score=search.min_trust_score,
            ends_at=listing.ends_at,
        )
        if not qualifies:
            continue

        alert = WatchAlert(
            saved_search_id=search.id,
            platform_listing_id=listing.platform_listing_id,
            title=listing.title,
            price=listing.price,
            currency=listing.currency,
            trust_score=trust.composite_score,
            url=listing.url,
        )
        _, is_new = user_store.upsert_alert(alert)
        if is_new:
            new_alert_count += 1
            log.info(
                "Monitor: new alert — search %d, listing %s, score=%d",
                search.id, listing.platform_listing_id, trust.composite_score,
            )

    user_store.mark_search_checked(search.id)
    log.info(
        "Monitor: search %d done — %d new alerts from %d listings",
        search.id, new_alert_count, len(raw_listings),
    )
    return new_alert_count
