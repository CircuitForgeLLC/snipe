from .metadata import MetadataScorer
from .photo import PhotoScorer
from .aggregator import Aggregator
from app.db.models import Seller, Listing, TrustScore
from app.db.store import Store
import hashlib
import math


class TrustScorer:
    """Orchestrates metadata + photo scoring for a batch of listings."""

    def __init__(self, shared_store: Store):
        self._store = shared_store
        self._meta = MetadataScorer()
        self._photo = PhotoScorer()
        self._agg = Aggregator()

    def score_batch(
        self,
        listings: list[Listing],
        query: str,
    ) -> list[TrustScore]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        comp = self._store.get_market_comp("ebay", query_hash)
        market_median = comp.median_price if comp else None

        # Coefficient of variation: stddev/mean across batch prices.
        # None when fewer than 2 priced listings (can't compute variance).
        _prices = [l.price for l in listings if l.price > 0]
        if len(_prices) >= 2:
            _mean = sum(_prices) / len(_prices)
            _stddev = math.sqrt(sum((p - _mean) ** 2 for p in _prices) / len(_prices))
            price_cv: float | None = _stddev / _mean if _mean > 0 else None
        else:
            price_cv = None

        photo_url_sets = [l.photo_urls for l in listings]
        duplicates = self._photo.check_duplicates(photo_url_sets)

        scores = []
        for listing, is_dup in zip(listings, duplicates):
            seller = self._store.get_seller("ebay", listing.seller_platform_id)
            if seller:
                signal_scores = self._meta.score(seller, market_median, listing.price, price_cv)
            else:
                signal_scores = {k: None for k in
                                 ["account_age", "feedback_count", "feedback_ratio",
                                  "price_vs_market", "category_history"]}
            trust = self._agg.aggregate(
                signal_scores, is_dup, seller,
                listing_id=listing.id or 0,
                listing_title=listing.title,
                times_seen=listing.times_seen,
                first_seen_at=listing.first_seen_at,
                price=listing.price,
                price_at_first_seen=listing.price_at_first_seen,
            )
            scores.append(trust)
        return scores
