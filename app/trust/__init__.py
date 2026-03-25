from .metadata import MetadataScorer
from .photo import PhotoScorer
from .aggregator import Aggregator
from app.db.models import Seller, Listing, TrustScore
from app.db.store import Store
import hashlib


class TrustScorer:
    """Orchestrates metadata + photo scoring for a batch of listings."""

    def __init__(self, store: Store):
        self._store = store
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

        photo_url_sets = [l.photo_urls for l in listings]
        duplicates = self._photo.check_duplicates(photo_url_sets)

        scores = []
        for listing, is_dup in zip(listings, duplicates):
            seller = self._store.get_seller("ebay", listing.seller_platform_id)
            if seller:
                signal_scores = self._meta.score(seller, market_median, listing.price)
            else:
                signal_scores = {k: None for k in
                                 ["account_age", "feedback_count", "feedback_ratio",
                                  "price_vs_market", "category_history"]}
            trust = self._agg.aggregate(signal_scores, is_dup, seller, listing.id or 0)
            scores.append(trust)
        return scores
