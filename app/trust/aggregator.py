"""Composite score and red flag extraction."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Optional
from app.db.models import Seller, TrustScore

HARD_FILTER_AGE_DAYS = 7
HARD_FILTER_BAD_RATIO_MIN_COUNT = 20
HARD_FILTER_BAD_RATIO_THRESHOLD = 0.80

# Sellers above this feedback count are treated as established retailers.
# Stock photo reuse (duplicate_photo) is suppressed for them — large retailers
# legitimately share manufacturer images across many listings.
_ESTABLISHED_RETAILER_FEEDBACK_THRESHOLD = 1000

# Title keywords that suggest cosmetic damage or wear (free-tier title scan).
# Description-body scan (paid BSL feature) runs via BTF enrichment — not implemented yet.
_SCRATCH_DENT_KEYWORDS = frozenset([
    # Explicit cosmetic damage
    "scratch", "scratched", "scratches", "scuff", "scuffed",
    "dent", "dented", "ding", "dinged",
    "crack", "cracked", "chip", "chipped",
    "damage", "damaged", "cosmetic damage",
    "blemish", "wear", "worn", "worn in",
    # Parts / condition catch-alls
    "as is", "for parts", "parts only", "spares or repair", "parts or repair",
    # Evasive redirects — seller hiding damage detail in listing body
    "see description", "read description", "read listing", "see listing",
    "see photos for", "see pics for", "see images for",
    # Functional problem phrases (phrases > single words to avoid false positives)
    "issue with", "issues with", "problem with", "problems with",
    "not working", "stopped working", "doesn't work", "does not work",
    "no power", "dead on arrival", "powers on but", "turns on but", "boots but",
    "faulty", "broken screen", "broken hinge", "broken port",
    # DIY / project / repair listings
    "needs repair", "needs work", "needs tlc",
    "project unit", "project item", "project laptop", "project phone",
    "for repair", "sold as is",
])


def _has_damage_keywords(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in _SCRATCH_DENT_KEYWORDS)


_LONG_ON_MARKET_MIN_SIGHTINGS = 5
_LONG_ON_MARKET_MIN_DAYS = 14
_PRICE_DROP_THRESHOLD = 0.20   # 20% below first-seen price


def _days_since(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        # Normalize to naive UTC so both paths (timezone-aware ISO and SQLite
        # CURRENT_TIMESTAMP naive strings) compare correctly.
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return (datetime.utcnow() - dt).days
    except ValueError:
        return None


class Aggregator:
    def aggregate(
        self,
        signal_scores: dict[str, Optional[int]],
        photo_hash_duplicate: bool,
        seller: Optional[Seller],
        listing_id: int = 0,
        listing_title: str = "",
        times_seen: int = 1,
        first_seen_at: Optional[str] = None,
        price: float = 0.0,
        price_at_first_seen: Optional[float] = None,
    ) -> TrustScore:
        is_partial = any(v is None for v in signal_scores.values())
        clean = {k: (v if v is not None else 0) for k, v in signal_scores.items()}

        # Score only against signals that returned real data — treating "no data"
        # as 0 conflates "bad signal" with "missing signal" and drags scores down
        # unfairly when the API doesn't expose a field (e.g. registrationDate).
        available = [v for v in signal_scores.values() if v is not None]
        available_max = len(available) * 20
        if available_max > 0:
            composite = round((sum(available) / available_max) * 100)
        else:
            composite = 0

        red_flags: list[str] = []

        # Hard filters
        if seller and seller.account_age_days is not None and seller.account_age_days < HARD_FILTER_AGE_DAYS:
            red_flags.append("new_account")
        if seller and (
            seller.feedback_ratio < HARD_FILTER_BAD_RATIO_THRESHOLD
            and seller.feedback_count > HARD_FILTER_BAD_RATIO_MIN_COUNT
        ):
            red_flags.append("established_bad_actor")

        # Soft flags
        if seller and seller.account_age_days is not None and seller.account_age_days < 30:
            red_flags.append("account_under_30_days")
        if seller and seller.feedback_count < 10:
            red_flags.append("low_feedback_count")
        if signal_scores.get("price_vs_market") == 0:  # only flag when data exists and price is genuinely <50% of market
            red_flags.append("suspicious_price")
        is_established_retailer = (
            seller is not None
            and seller.feedback_count >= _ESTABLISHED_RETAILER_FEEDBACK_THRESHOLD
        )
        if photo_hash_duplicate and not is_established_retailer:
            red_flags.append("duplicate_photo")
        if listing_title and _has_damage_keywords(listing_title):
            red_flags.append("scratch_dent_mentioned")

        # Staging DB signals
        days_in_index = _days_since(first_seen_at)
        if (times_seen >= _LONG_ON_MARKET_MIN_SIGHTINGS
                and days_in_index is not None
                and days_in_index >= _LONG_ON_MARKET_MIN_DAYS):
            red_flags.append("long_on_market")
        if (price_at_first_seen and price_at_first_seen > 0
                and price < price_at_first_seen * (1 - _PRICE_DROP_THRESHOLD)):
            red_flags.append("significant_price_drop")

        return TrustScore(
            listing_id=listing_id,
            composite_score=composite,
            account_age_score=clean["account_age"],
            feedback_count_score=clean["feedback_count"],
            feedback_ratio_score=clean["feedback_ratio"],
            price_vs_market_score=clean["price_vs_market"],
            category_history_score=clean["category_history"],
            photo_hash_duplicate=photo_hash_duplicate,
            red_flags_json=json.dumps(red_flags),
            score_is_partial=is_partial,
        )
