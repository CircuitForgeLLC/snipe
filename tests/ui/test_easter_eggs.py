"""Tests for easter egg helpers (pure logic — no Streamlit calls)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.db.models import Listing, TrustScore
from app.ui.components.easter_eggs import auction_hours_remaining, is_steal


def _listing(**kwargs) -> Listing:
    defaults = dict(
        platform="ebay",
        platform_listing_id="1",
        title="Test",
        price=800.0,
        currency="USD",
        condition="used",
        seller_platform_id="seller1",
        url="https://ebay.com/itm/1",
        buying_format="fixed_price",
        ends_at=None,
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def _trust(score: int, flags: list[str] | None = None) -> TrustScore:
    return TrustScore(
        listing_id=1,
        composite_score=score,
        account_age_score=20,
        feedback_count_score=20,
        feedback_ratio_score=20,
        price_vs_market_score=20,
        category_history_score=score - 80 if score >= 80 else 0,
        red_flags_json=json.dumps(flags or []),
    )


# ---------------------------------------------------------------------------
# is_steal
# ---------------------------------------------------------------------------

class TestIsSteal:
    def test_qualifies_when_high_trust_and_20_pct_below(self):
        listing = _listing(price=840.0)  # 16% below 1000
        trust = _trust(92)
        assert is_steal(listing, trust, market_price=1000.0) is True

    def test_fails_when_trust_below_90(self):
        listing = _listing(price=840.0)
        trust = _trust(89)
        assert is_steal(listing, trust, market_price=1000.0) is False

    def test_fails_when_discount_too_deep(self):
        # 35% below market — suspicious, not a steal
        listing = _listing(price=650.0)
        trust = _trust(95)
        assert is_steal(listing, trust, market_price=1000.0) is False

    def test_fails_when_discount_too_shallow(self):
        # 10% below market — not enough of a deal
        listing = _listing(price=900.0)
        trust = _trust(95)
        assert is_steal(listing, trust, market_price=1000.0) is False

    def test_fails_when_suspicious_price_flag(self):
        listing = _listing(price=840.0)
        trust = _trust(92, flags=["suspicious_price"])
        assert is_steal(listing, trust, market_price=1000.0) is False

    def test_fails_when_no_market_price(self):
        listing = _listing(price=840.0)
        trust = _trust(92)
        assert is_steal(listing, trust, market_price=None) is False

    def test_fails_when_no_trust(self):
        listing = _listing(price=840.0)
        assert is_steal(listing, None, market_price=1000.0) is False

    def test_boundary_15_pct(self):
        listing = _listing(price=850.0)  # exactly 15% below 1000
        trust = _trust(92)
        assert is_steal(listing, trust, market_price=1000.0) is True

    def test_boundary_30_pct(self):
        listing = _listing(price=700.0)  # exactly 30% below 1000
        trust = _trust(92)
        assert is_steal(listing, trust, market_price=1000.0) is True


# ---------------------------------------------------------------------------
# auction_hours_remaining
# ---------------------------------------------------------------------------

class TestAuctionHoursRemaining:
    def _auction_listing(self, hours_ahead: float) -> Listing:
        ends = (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).isoformat()
        return _listing(buying_format="auction", ends_at=ends)

    def test_returns_hours_for_active_auction(self):
        listing = self._auction_listing(3.0)
        h = auction_hours_remaining(listing)
        assert h is not None
        assert 2.9 < h < 3.1

    def test_returns_none_for_fixed_price(self):
        listing = _listing(buying_format="fixed_price")
        assert auction_hours_remaining(listing) is None

    def test_returns_none_when_no_ends_at(self):
        listing = _listing(buying_format="auction", ends_at=None)
        assert auction_hours_remaining(listing) is None

    def test_returns_zero_for_ended_auction(self):
        ends = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        listing = _listing(buying_format="auction", ends_at=ends)
        h = auction_hours_remaining(listing)
        assert h == 0.0
