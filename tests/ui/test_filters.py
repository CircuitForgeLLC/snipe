from app.db.models import Listing, TrustScore
from app.ui.components.filters import build_filter_options


def _listing(price, condition, score):
    return (
        Listing("ebay", "1", "GPU", price, "USD", condition, "u", "https://ebay.com", [], 1),
        TrustScore(0, score, 10, 10, 10, 10, 10),
    )


def test_price_range_from_results():
    pairs = [_listing(500, "used", 80), _listing(1200, "new", 60)]
    opts = build_filter_options(pairs)
    assert opts.price_min == 500
    assert opts.price_max == 1200


def test_conditions_from_results():
    pairs = [_listing(500, "used", 80), _listing(1200, "new", 60), _listing(800, "used", 70)]
    opts = build_filter_options(pairs)
    assert "used" in opts.conditions
    assert opts.conditions["used"] == 2
    assert opts.conditions["new"] == 1


def test_missing_condition_not_included():
    pairs = [_listing(500, "used", 80)]
    opts = build_filter_options(pairs)
    assert "new" not in opts.conditions


def test_trust_score_bands():
    pairs = [_listing(500, "used", 85), _listing(700, "new", 60), _listing(400, "used", 20)]
    opts = build_filter_options(pairs)
    assert opts.score_bands["safe"] == 1    # 80+
    assert opts.score_bands["review"] == 1  # 50–79
    assert opts.score_bands["skip"] == 1    # <50
