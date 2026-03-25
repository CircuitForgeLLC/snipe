from app.db.models import Seller
from app.trust.metadata import MetadataScorer


def _seller(**kwargs) -> Seller:
    defaults = dict(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=730, feedback_count=450,
        feedback_ratio=0.991, category_history_json='{"ELECTRONICS": 30}',
    )
    defaults.update(kwargs)
    return Seller(**defaults)


def test_established_seller_scores_high():
    scorer = MetadataScorer()
    scores = scorer.score(_seller(), market_median=1000.0, listing_price=950.0)
    total = sum(scores.values())
    assert total >= 80


def test_new_account_scores_zero_on_age():
    scorer = MetadataScorer()
    scores = scorer.score(_seller(account_age_days=3), market_median=1000.0, listing_price=950.0)
    assert scores["account_age"] == 0


def test_low_feedback_count_scores_low():
    scorer = MetadataScorer()
    scores = scorer.score(_seller(feedback_count=2), market_median=1000.0, listing_price=950.0)
    assert scores["feedback_count"] < 10


def test_suspicious_price_scores_zero():
    scorer = MetadataScorer()
    # 60% below market → zero
    scores = scorer.score(_seller(), market_median=1000.0, listing_price=400.0)
    assert scores["price_vs_market"] == 0


def test_no_market_data_returns_none():
    scorer = MetadataScorer()
    scores = scorer.score(_seller(), market_median=None, listing_price=950.0)
    # None signals "data unavailable" — aggregator will set score_is_partial=True
    assert scores["price_vs_market"] is None
