"""MercariAdapter — scraper-based Mercari platform adapter.

Trust signal coverage vs eBay:
  ✅ feedback_count    (NumSales from listing page)
  ✅ feedback_ratio    (ReviewStarsWrapper data-stars / 5)
  ❌ account_age_days  (requires seller profile page — future work)
  ❌ category_history  (not exposed in HTML — future work)
  ✅ price_vs_market   (computed by trust scorer from comps, same as eBay)

Because account_age and category_history are always None, TrustScore.score_is_partial
will be True for all Mercari results.  The aggregator handles this correctly
by scoring only from available signals.

seller_platform_id on Listing objects holds the product_id (e.g. "m86032668393")
rather than the seller username, because search results don't expose seller identity.
get_seller() resolves the product_id → seller by fetching the listing page.
The DB lookup key is (platform="mercari", platform_seller_id=product_id).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from app.db.models import Listing, Seller
from app.db.store import Store
from app.platforms import PlatformAdapter, SearchFilters
from app.platforms.mercari.scraper import (
    build_search_url,
    parse_listing_html,
    parse_search_html,
)

log = logging.getLogger(__name__)

_SELLER_CACHE_TTL_HOURS = 6
_BETWEEN_LISTING_FETCH_SECS = 1.5


class MercariAdapter(PlatformAdapter):
    def __init__(self, store: Store) -> None:
        self._store = store

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        from app.platforms.ebay.browser_pool import get_pool

        url = build_search_url(query, filters.max_price, filters.min_price)
        log.info("mercari: fetching search URL: %s", url)

        html = get_pool().fetch_html(
            url,
            delay=1.0,
            wait_for_timeout_ms=8000,
        )
        raw_listings = parse_search_html(html)

        listings: list[Listing] = []
        seen: set[str] = set()
        for raw in raw_listings:
            pid = raw["product_id"]
            if pid in seen:
                continue
            seen.add(pid)
            listings.append(_normalise_listing(raw, query))

        log.info("mercari: parsed %d listings for %r", len(listings), query)

        # Client-side keyword filter (mirrors eBay scraper behaviour).
        if filters.must_include:
            listings = _apply_keyword_filter(listings, filters.must_include, filters.must_include_mode)
        if filters.must_exclude:
            listings = _apply_exclude_filter(listings, filters.must_exclude)

        return listings

    def get_seller(self, seller_platform_id: str) -> Optional[Seller]:
        """Fetch seller data from the listing page identified by seller_platform_id.

        For Mercari, seller_platform_id is the product_id (e.g. "m86032668393")
        because seller usernames aren't available from search results HTML.
        """
        cached = self._store.get_seller("mercari", seller_platform_id)
        if cached:
            return cached

        from app.platforms.ebay.browser_pool import get_pool

        url = f"https://www.mercari.com/us/item/{seller_platform_id}/"
        try:
            time.sleep(_BETWEEN_LISTING_FETCH_SECS)
            html = get_pool().fetch_html(
                url,
                delay=0.5,
                wait_for_timeout_ms=6000,
            )
            raw = parse_listing_html(html, seller_platform_id)
            seller = _normalise_seller(raw)
            self._store.save_seller(seller)
            return seller
        except Exception as exc:
            log.warning("mercari: get_seller failed for %s: %s", seller_platform_id, exc)
            return None

    def get_completed_sales(self, query: str, pages: int = 1) -> list[Listing]:
        """Mercari sold-listing comps — stubbed for Phase 3.

        Mercari exposes sold listings via ?status=ITEM_STATUS_TRADING but the
        data is sparse.  Phase 3 will implement comp extraction here; for now
        the trust scorer falls back to price_vs_market=None (partial score).
        """
        return []


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_listing(raw: dict, query: str) -> Listing:
    return Listing(
        platform="mercari",
        platform_listing_id=raw["product_id"],
        title=raw["title"],
        price=raw["price"],
        currency="USD",
        condition="",       # not available from search results; get_seller() populates this
        seller_platform_id=raw["product_id"],  # see module docstring
        url=raw["url"],
        photo_urls=[raw["photo_url"]] if raw.get("photo_url") else [],
        listing_age_days=0,
        buying_format="fixed_price",
        category_name=None,
    )


def _normalise_seller(raw: dict) -> Seller:
    stars = raw.get("stars", 0.0)
    feedback_ratio = min(stars / 5.0, 1.0) if stars > 0 else 0.0

    return Seller(
        platform="mercari",
        platform_seller_id=raw["product_id"],
        username=raw.get("username", ""),
        account_age_days=None,           # not available without seller profile page
        feedback_count=raw.get("num_sales", 0),
        feedback_ratio=feedback_ratio,
        category_history_json=json.dumps({}),
    )


def _apply_keyword_filter(listings: list[Listing], must_include: list[str], mode: str) -> list[Listing]:
    if not must_include:
        return listings

    def _matches(listing: Listing) -> bool:
        title = listing.title.lower()
        if mode == "any":
            return any(kw.lower() in title for kw in must_include)
        # "all" (default) and "groups" both require all terms present
        return all(kw.lower() in title for kw in must_include)

    return [l for l in listings if _matches(l)]


def _apply_exclude_filter(listings: list[Listing], must_exclude: list[str]) -> list[Listing]:
    if not must_exclude:
        return listings

    def _clean(listing: Listing) -> bool:
        title = listing.title.lower()
        return not any(term.lower() in title for term in must_exclude)

    return [l for l in listings if _clean(l)]
