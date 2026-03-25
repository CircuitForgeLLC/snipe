"""Five metadata trust signals, each scored 0–20."""
from __future__ import annotations
import json
from typing import Optional
from app.db.models import Seller

ELECTRONICS_CATEGORIES = {"ELECTRONICS", "COMPUTERS_TABLETS", "VIDEO_GAMES", "CELL_PHONES"}


class MetadataScorer:
    def score(
        self,
        seller: Seller,
        market_median: Optional[float],
        listing_price: float,
    ) -> dict[str, Optional[int]]:
        return {
            "account_age":      self._account_age(seller.account_age_days),
            "feedback_count":   self._feedback_count(seller.feedback_count),
            "feedback_ratio":   self._feedback_ratio(seller.feedback_ratio, seller.feedback_count),
            "price_vs_market":  self._price_vs_market(listing_price, market_median),
            "category_history": self._category_history(seller.category_history_json),
        }

    def _account_age(self, days: int) -> int:
        if days < 7:   return 0
        if days < 30:  return 5
        if days < 90:  return 10
        if days < 365: return 15
        return 20

    def _feedback_count(self, count: int) -> int:
        if count < 3:   return 0
        if count < 10:  return 5
        if count < 50:  return 10
        if count < 200: return 15
        return 20

    def _feedback_ratio(self, ratio: float, count: int) -> int:
        if ratio < 0.80 and count > 20: return 0
        if ratio < 0.90: return 5
        if ratio < 0.95: return 10
        if ratio < 0.98: return 15
        return 20

    def _price_vs_market(self, price: float, median: Optional[float]) -> Optional[int]:
        if median is None: return None  # data unavailable → aggregator sets score_is_partial
        if median <= 0:    return None
        ratio = price / median
        if ratio < 0.50:  return 0   # >50% below = scam
        if ratio < 0.70:  return 5   # >30% below = suspicious
        if ratio < 0.85:  return 10
        if ratio <= 1.20: return 20
        return 15  # above market = still ok, just expensive

    def _category_history(self, category_history_json: str) -> int:
        try:
            history = json.loads(category_history_json)
        except (ValueError, TypeError):
            return 0
        electronics_sales = sum(
            v for k, v in history.items() if k in ELECTRONICS_CATEGORIES
        )
        if electronics_sales == 0: return 0
        if electronics_sales < 5:  return 8
        if electronics_sales < 20: return 14
        return 20
