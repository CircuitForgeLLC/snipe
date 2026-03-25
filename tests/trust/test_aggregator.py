from app.db.models import Seller
from app.trust.aggregator import Aggregator


def test_composite_sum_of_five_signals():
    agg = Aggregator()
    scores = {
        "account_age": 18, "feedback_count": 16,
        "feedback_ratio": 20, "price_vs_market": 15,
        "category_history": 14,
    }
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=None)
    assert result.composite_score == 83


def test_hard_filter_new_account():
    agg = Aggregator()
    scores = {k: 20 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    young_seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=3, feedback_count=0,
        feedback_ratio=1.0, category_history_json="{}",
    )
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=young_seller)
    assert "new_account" in result.red_flags_json


def test_hard_filter_bad_actor_established_account():
    """Established account (count > 20) with very bad ratio → hard filter."""
    agg = Aggregator()
    scores = {k: 10 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    bad_seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=730, feedback_count=25,  # count > 20
        feedback_ratio=0.70,                       # ratio < 80% → hard filter
        category_history_json="{}",
    )
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=bad_seller)
    assert "established_bad_actor" in result.red_flags_json


def test_partial_score_flagged_when_signals_missing():
    agg = Aggregator()
    scores = {
        "account_age": 18, "feedback_count": None,  # None = unavailable
        "feedback_ratio": 20, "price_vs_market": 15,
        "category_history": 14,
    }
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=None)
    assert result.score_is_partial is True
