from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Listing, MarketComp, Seller
from app.db.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def test_store_creates_tables(store):
    # If no exception on init, tables exist
    pass


def test_save_and_get_seller(store):
    seller = Seller(
        platform="ebay",
        platform_seller_id="user123",
        username="techseller",
        account_age_days=730,
        feedback_count=450,
        feedback_ratio=0.991,
        category_history_json="{}",
    )
    store.save_seller(seller)
    result = store.get_seller("ebay", "user123")
    assert result is not None
    assert result.username == "techseller"
    assert result.feedback_count == 450


def test_save_and_get_listing(store):
    listing = Listing(
        platform="ebay",
        platform_listing_id="ebay-123",
        title="RTX 4090 FE",
        price=950.00,
        currency="USD",
        condition="used",
        seller_platform_id="user123",
        url="https://ebay.com/itm/123",
        photo_urls=["https://i.ebayimg.com/1.jpg"],
        listing_age_days=3,
    )
    store.save_listing(listing)
    result = store.get_listing("ebay", "ebay-123")
    assert result is not None
    assert result.title == "RTX 4090 FE"
    assert result.price == 950.00


def test_save_and_get_market_comp(store):
    comp = MarketComp(
        platform="ebay",
        query_hash="abc123",
        median_price=1050.0,
        sample_count=12,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
    )
    store.save_market_comp(comp)
    result = store.get_market_comp("ebay", "abc123")
    assert result is not None
    assert result.median_price == 1050.0


def test_get_market_comp_returns_none_for_expired(store):
    comp = MarketComp(
        platform="ebay",
        query_hash="expired",
        median_price=900.0,
        sample_count=5,
        expires_at="2020-01-01T00:00:00",  # past
    )
    store.save_market_comp(comp)
    result = store.get_market_comp("ebay", "expired")
    assert result is None
