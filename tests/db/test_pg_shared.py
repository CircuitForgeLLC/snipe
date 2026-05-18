"""Tests for SnipeSharedStore — requires live Postgres via SNIPE_SHARED_DB_URL."""
import pytest
from app.db.models import MarketComp, Seller
from app.db.pg_shared import SnipeSharedDB, SnipeSharedStore
from app.db.protocol import SharedTableProtocol


@pytest.mark.postgres
def test_snipe_shared_store_satisfies_protocol(postgres_dsn):
    assert issubclass(SnipeSharedStore, SharedTableProtocol)


@pytest.mark.postgres
def test_save_and_get_seller(postgres_dsn):
    db = SnipeSharedDB(postgres_dsn)
    db.run_migrations()
    store = SnipeSharedStore(db)

    seller = Seller(
        platform="ebay",
        platform_seller_id="test-seller-001",
        username="testseller",
        account_age_days=365,
        feedback_count=100,
        feedback_ratio=0.99,
        category_history_json='{"electronics": 5}',
    )
    store.save_seller(seller)

    result = store.get_seller("ebay", "test-seller-001")
    assert result is not None
    assert result.username == "testseller"
    assert result.feedback_count == 100

    store.delete_seller_data("ebay", "test-seller-001")
    db.close()


@pytest.mark.postgres
def test_save_sellers_coalesce_preserves_age(postgres_dsn):
    db = SnipeSharedDB(postgres_dsn)
    db.run_migrations()
    store = SnipeSharedStore(db)

    seller_with_age = Seller(
        platform="ebay", platform_seller_id="coalesce-test",
        username="u", account_age_days=730,
        feedback_count=50, feedback_ratio=0.95, category_history_json="{}",
    )
    store.save_seller(seller_with_age)

    seller_without_age = Seller(
        platform="ebay", platform_seller_id="coalesce-test",
        username="u", account_age_days=None,
        feedback_count=60, feedback_ratio=0.96, category_history_json="{}",
    )
    store.save_sellers([seller_without_age])

    result = store.get_seller("ebay", "coalesce-test")
    assert result.account_age_days == 730
    assert result.feedback_count == 60

    store.delete_seller_data("ebay", "coalesce-test")
    db.close()


@pytest.mark.postgres
def test_market_comp_cache(postgres_dsn):
    from datetime import datetime, timedelta, timezone
    db = SnipeSharedDB(postgres_dsn)
    db.run_migrations()
    store = SnipeSharedStore(db)

    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    comp = MarketComp(
        platform="ebay", query_hash="abc123",
        median_price=49.99, sample_count=10, expires_at=expires,
    )
    store.save_market_comp(comp)

    result = store.get_market_comp("ebay", "abc123")
    assert result is not None
    assert result.median_price == 49.99

    db.close()


@pytest.mark.postgres
def test_reported_sellers(postgres_dsn):
    db = SnipeSharedDB(postgres_dsn)
    db.run_migrations()
    store = SnipeSharedStore(db)

    store.mark_reported("ebay", "bad-seller-99", username="badguy")
    reported = store.list_reported("ebay")
    assert "bad-seller-99" in reported

    store.mark_reported("ebay", "bad-seller-99")  # idempotent

    db.close()


@pytest.mark.postgres
def test_clone_returns_self(postgres_dsn):
    db = SnipeSharedDB(postgres_dsn)
    store = SnipeSharedStore(db)
    assert store.clone() is store
    db.close()
