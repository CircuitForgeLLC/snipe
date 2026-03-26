"""Composite score and red flag extraction."""
from __future__ import annotations
import json
from typing import Optional
from app.db.models import Seller, TrustScore

HARD_FILTER_AGE_DAYS = 7
HARD_FILTER_BAD_RATIO_MIN_COUNT = 20
HARD_FILTER_BAD_RATIO_THRESHOLD = 0.80


class Aggregator:
    def aggregate(
        self,
        signal_scores: dict[str, Optional[int]],
        photo_hash_duplicate: bool,
        seller: Optional[Seller],
        listing_id: int = 0,
    ) -> TrustScore:
        is_partial = any(v is None for v in signal_scores.values())
        clean = {k: (v if v is not None else 0) for k, v in signal_scores.items()}
        composite = sum(clean.values())

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
        if photo_hash_duplicate:
            red_flags.append("duplicate_photo")

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
