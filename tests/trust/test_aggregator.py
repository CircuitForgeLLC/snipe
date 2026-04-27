from datetime import datetime, timedelta, timezone

from app.db.models import Seller
from app.trust.aggregator import Aggregator

_ALL_20 = {k: 20 for k in ["account_age", "feedback_count", "feedback_ratio", "price_vs_market", "category_history"]}


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


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


def test_suspicious_price_not_flagged_when_market_data_absent():
    """None price_vs_market (no market comp) must NOT trigger suspicious_price.

    Regression guard: clean[] replaces None with 0, so naive `clean[...] == 0`
    would fire even when the signal is simply unavailable.
    """
    agg = Aggregator()
    scores = {
        "account_age": 15, "feedback_count": 15,
        "feedback_ratio": 20, "price_vs_market": None,  # no market data
        "category_history": 0,
    }
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=None)
    assert "suspicious_price" not in result.red_flags_json


def test_suspicious_price_flagged_when_price_genuinely_low():
    """price_vs_market == 0 (explicitly, meaning >50% below median) → flag fires."""
    agg = Aggregator()
    scores = {
        "account_age": 15, "feedback_count": 15,
        "feedback_ratio": 20, "price_vs_market": 0,  # price is scam-level low
        "category_history": 0,
    }
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=None)
    assert "suspicious_price" in result.red_flags_json


def test_scratch_dent_flagged_from_title_slash_variant():
    """Title containing 'parts/repair' (slash variant, no 'or') must trigger scratch_dent_mentioned."""
    agg = Aggregator()
    scores = {k: 15 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    result = agg.aggregate(
        scores, photo_hash_duplicate=False, seller=None,
        listing_title="Generic Widget XL - Parts/Repair",
    )
    assert "scratch_dent_mentioned" in result.red_flags_json


def test_scratch_dent_flagged_from_condition_field():
    """eBay formal condition 'for parts or not working' must trigger scratch_dent_mentioned
    even when the listing title contains no damage keywords."""
    agg = Aggregator()
    scores = {k: 15 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    result = agg.aggregate(
        scores, photo_hash_duplicate=False, seller=None,
        listing_title="Generic Widget XL",
        listing_condition="for parts or not working",
    )
    assert "scratch_dent_mentioned" in result.red_flags_json


def test_scratch_dent_not_flagged_for_clean_listing():
    """Clean title + 'New' condition must NOT trigger scratch_dent_mentioned."""
    agg = Aggregator()
    scores = {k: 15 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    result = agg.aggregate(
        scores, photo_hash_duplicate=False, seller=None,
        listing_title="Generic Widget XL",
        listing_condition="new",
    )
    assert "scratch_dent_mentioned" not in result.red_flags_json


def test_new_account_not_flagged_when_age_absent():
    """account_age_days=None (scraper tier) must NOT trigger new_account or account_under_30_days."""
    agg = Aggregator()
    scores = {k: 10 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    scraper_seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=None,  # not fetched at scraper tier
        feedback_count=50, feedback_ratio=0.99, category_history_json="{}",
    )
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=scraper_seller)
    assert "new_account" not in result.red_flags_json
    assert "account_under_30_days" not in result.red_flags_json


# ── zero_feedback ─────────────────────────────────────────────────────────────

def test_zero_feedback_adds_flag():
    """seller.feedback_count == 0 must add zero_feedback flag."""
    agg = Aggregator()
    seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=365, feedback_count=0, feedback_ratio=1.0,
        category_history_json="{}",
    )
    result = agg.aggregate(_ALL_20.copy(), photo_hash_duplicate=False, seller=seller)
    assert "zero_feedback" in result.red_flags_json


def test_zero_feedback_caps_composite_at_35():
    """Even with perfect other signals (all 20/20), zero feedback caps composite at 35."""
    agg = Aggregator()
    seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=365, feedback_count=0, feedback_ratio=1.0,
        category_history_json="{}",
    )
    result = agg.aggregate(_ALL_20.copy(), photo_hash_duplicate=False, seller=seller)
    assert result.composite_score <= 35


# ── long_on_market ────────────────────────────────────────────────────────────

def test_long_on_market_flagged_when_thresholds_met():
    """times_seen >= 5 AND listing age >= 14 days → long_on_market fires."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        times_seen=5, first_seen_at=_iso_days_ago(20),
    )
    assert "long_on_market" in result.red_flags_json


def test_long_on_market_not_flagged_when_too_few_sightings():
    """times_seen < 5 must NOT trigger long_on_market even if listing is old."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        times_seen=4, first_seen_at=_iso_days_ago(30),
    )
    assert "long_on_market" not in result.red_flags_json


def test_long_on_market_not_flagged_when_too_recent():
    """times_seen >= 5 but only seen for < 14 days → long_on_market must NOT fire."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        times_seen=10, first_seen_at=_iso_days_ago(5),
    )
    assert "long_on_market" not in result.red_flags_json


# ── significant_price_drop ────────────────────────────────────────────────────

def test_significant_price_drop_flagged():
    """price >= 20% below price_at_first_seen → significant_price_drop fires."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        price=75.00, price_at_first_seen=100.00,  # 25% drop
    )
    assert "significant_price_drop" in result.red_flags_json


def test_significant_price_drop_not_flagged_when_drop_is_small():
    """< 20% drop must NOT trigger significant_price_drop."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        price=95.00, price_at_first_seen=100.00,  # 5% drop
    )
    assert "significant_price_drop" not in result.red_flags_json


def test_significant_price_drop_not_flagged_when_no_prior_price():
    """price_at_first_seen=None (first sighting) must NOT fire significant_price_drop."""
    agg = Aggregator()
    result = agg.aggregate(
        _ALL_20.copy(), photo_hash_duplicate=False, seller=None,
        price=50.00, price_at_first_seen=None,
    )
    assert "significant_price_drop" not in result.red_flags_json


# ── declining_ratio (high-volume seller edge case, snipe#52) ─────────────────

def test_declining_ratio_soft_flag_for_high_volume_seller():
    """High-volume seller (count > 500) with declining but not catastrophic ratio
    gets declining_ratio soft flag, NOT the hard established_bad_actor flag.

    Edge case: 12-month ratio may reflect only a small recent sample for sellers
    with large lifetime feedback counts — hard-flagging is disproportionate.
    """
    agg = Aggregator()
    scores = {k: 10 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    high_vol = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=2000, feedback_count=800,  # count > 500
        feedback_ratio=0.75,                         # < 0.80 but > 0.60
        category_history_json="{}",
    )
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=high_vol)
    assert "declining_ratio" in result.red_flags_json
    assert "established_bad_actor" not in result.red_flags_json


def test_established_bad_actor_still_fires_for_catastrophic_high_volume_ratio():
    """High-volume seller (count > 500) with catastrophically bad ratio (< 60%)
    still gets the hard established_bad_actor flag — not just declining_ratio."""
    agg = Aggregator()
    scores = {k: 10 for k in ["account_age", "feedback_count",
                               "feedback_ratio", "price_vs_market", "category_history"]}
    bad_high_vol = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=2000, feedback_count=800,
        feedback_ratio=0.50,  # < 0.60 threshold → still hard flag
        category_history_json="{}",
    )
    result = agg.aggregate(scores, photo_hash_duplicate=False, seller=bad_high_vol)
    assert "established_bad_actor" in result.red_flags_json
    assert "declining_ratio" not in result.red_flags_json


# ── established retailer ──────────────────────────────────────────────────────

def test_established_retailer_suppresses_duplicate_photo():
    """feedback_count >= 1000 (established retailer) must suppress duplicate_photo flag."""
    agg = Aggregator()
    retailer = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=1800, feedback_count=5000, feedback_ratio=0.99,
        category_history_json="{}",
    )
    result = agg.aggregate(_ALL_20.copy(), photo_hash_duplicate=True, seller=retailer)
    assert "duplicate_photo" not in result.red_flags_json


def test_non_retailer_does_not_suppress_duplicate_photo():
    """feedback_count < 1000 — duplicate_photo must still fire when hash matches."""
    agg = Aggregator()
    seller = Seller(
        platform="ebay", platform_seller_id="u", username="u",
        account_age_days=365, feedback_count=50, feedback_ratio=0.99,
        category_history_json="{}",
    )
    result = agg.aggregate(_ALL_20.copy(), photo_hash_duplicate=True, seller=seller)
    assert "duplicate_photo" in result.red_flags_json
