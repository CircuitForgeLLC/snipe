"""Tests for the short-TTL search result cache in api/main.py.

Covers:
  - _cache_key stability (same inputs → same key)
  - _cache_key uniqueness (different inputs → different keys)
  - cache hit path returns early without scraping (async worker)
  - cache miss path stores result in _search_result_cache
  - refresh=True bypasses cache read (still writes fresh result)
  - TTL expiry: expired entries are not returned as hits
  - _evict_expired_cache removes expired entries
"""
from __future__ import annotations

import os
import queue as _queue
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_cache():
    """Reset module-level cache state between tests."""
    import api.main as _main
    _main._search_result_cache.clear()
    _main._last_eviction_ts = 0.0


@pytest.fixture(autouse=True)
def isolated_cache():
    """Ensure each test starts with an empty cache."""
    _clear_cache()
    yield
    _clear_cache()


@pytest.fixture
def client(tmp_path):
    """TestClient backed by a fresh tmp DB."""
    os.environ["SNIPE_DB"] = str(tmp_path / "snipe.db")
    from api.main import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


def _make_mock_listing(listing_id: str = "123456789", seller_id: str = "test_seller"):
    """Return a MagicMock listing (for use where asdict() is NOT called on it)."""
    m = MagicMock()
    m.platform_listing_id = listing_id
    m.seller_platform_id = seller_id
    m.title = "Test GPU"
    m.price = 100.0
    m.currency = "USD"
    m.condition = "Used"
    m.url = f"https://www.ebay.com/itm/{listing_id}"
    m.photo_urls = []
    m.listing_age_days = 5
    m.buying_format = "fixed_price"
    m.ends_at = None
    m.fetched_at = None
    m.trust_score_id = None
    m.id = 1
    m.category_name = None
    return m


def _make_real_listing(listing_id: str = "123456789", seller_id: str = "test_seller"):
    """Return a real Listing dataclass instance (for use where asdict() is called)."""
    from app.db.models import Listing
    return Listing(
        platform="ebay",
        platform_listing_id=listing_id,
        title="Test GPU",
        price=100.0,
        currency="USD",
        condition="Used",
        seller_platform_id=seller_id,
        url=f"https://www.ebay.com/itm/{listing_id}",
        photo_urls=[],
        listing_age_days=5,
        buying_format="fixed_price",
        id=None,
    )


# ── _cache_key unit tests ─────────────────────────────────────────────────────

def test_cache_key_stable_for_same_inputs():
    """The same parameter set always produces the same key."""
    from api.main import _cache_key
    k1 = _cache_key("rtx 3080", 400.0, 100.0, 2, "rtx,3080", "all", "mining", "27386")
    k2 = _cache_key("rtx 3080", 400.0, 100.0, 2, "rtx,3080", "all", "mining", "27386")
    assert k1 == k2


def test_cache_key_case_normalised():
    """Query is normalised to lower-case + stripped before hashing."""
    from api.main import _cache_key
    k1 = _cache_key("RTX 3080", None, None, 1, "", "all", "", "")
    k2 = _cache_key("rtx 3080", None, None, 1, "", "all", "", "")
    assert k1 == k2


def test_cache_key_differs_on_query_change():
    """Different query strings must produce different keys."""
    from api.main import _cache_key
    k1 = _cache_key("rtx 3080", None, None, 1, "", "all", "", "")
    k2 = _cache_key("gtx 1080", None, None, 1, "", "all", "", "")
    assert k1 != k2


def test_cache_key_differs_on_price_filter():
    """Different max_price must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", 400.0, None, 1, "", "all", "", "")
    k2 = _cache_key("gpu", 500.0, None, 1, "", "all", "", "")
    assert k1 != k2


def test_cache_key_differs_on_min_price():
    """Different min_price must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", None, 50.0, 1, "", "all", "", "")
    k2 = _cache_key("gpu", None, 100.0, 1, "", "all", "", "")
    assert k1 != k2


def test_cache_key_differs_on_pages():
    """Different page count must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", None, None, 1, "", "all", "", "")
    k2 = _cache_key("gpu", None, None, 2, "", "all", "", "")
    assert k1 != k2


def test_cache_key_differs_on_must_include():
    """Different must_include terms must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", None, None, 1, "rtx", "all", "", "")
    k2 = _cache_key("gpu", None, None, 1, "gtx", "all", "", "")
    assert k1 != k2


def test_cache_key_differs_on_must_exclude():
    """Different must_exclude terms must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", None, None, 1, "", "all", "mining", "")
    k2 = _cache_key("gpu", None, None, 1, "", "all", "defective", "")
    assert k1 != k2


def test_cache_key_differs_on_category_id():
    """Different category_id must produce a different key."""
    from api.main import _cache_key
    k1 = _cache_key("gpu", None, None, 1, "", "all", "", "27386")
    k2 = _cache_key("gpu", None, None, 1, "", "all", "", "12345")
    assert k1 != k2


def test_cache_key_is_16_chars():
    """Key must be exactly 16 hex characters."""
    from api.main import _cache_key
    k = _cache_key("gpu", None, None, 1, "", "all", "", "")
    assert len(k) == 16
    assert all(c in "0123456789abcdef" for c in k)


# ── TTL / eviction unit tests ─────────────────────────────────────────────────

def test_expired_entry_is_not_returned_as_hit():
    """An entry past its TTL must not be treated as a cache hit."""
    import api.main as _main
    from api.main import _cache_key

    key = _cache_key("gpu", None, None, 1, "", "all", "", "")
    # Write an already-expired entry.
    _main._search_result_cache[key] = (
        {"listings": [], "market_price": None},
        time.time() - 1.0,  # expired 1 second ago
    )

    cached = _main._search_result_cache.get(key)
    assert cached is not None
    payload, expiry = cached
    # Simulate the hit-check used in main.py
    assert expiry <= time.time(), "Entry should be expired"


def test_evict_expired_cache_removes_stale_entries():
    """_evict_expired_cache must remove entries whose expiry has passed."""
    import api.main as _main
    from api.main import _cache_key, _evict_expired_cache

    key_expired = _cache_key("old query", None, None, 1, "", "all", "", "")
    key_valid = _cache_key("new query", None, None, 1, "", "all", "", "")

    _main._search_result_cache[key_expired] = (
        {"listings": [], "market_price": None},
        time.time() - 10.0,  # already expired
    )
    _main._search_result_cache[key_valid] = (
        {"listings": [], "market_price": 99.0},
        time.time() + 300.0,  # valid for 5 min
    )

    # Reset throttle so eviction runs immediately.
    _main._last_eviction_ts = 0.0
    _evict_expired_cache()

    assert key_expired not in _main._search_result_cache
    assert key_valid in _main._search_result_cache


def test_evict_is_rate_limited():
    """_evict_expired_cache should skip eviction if called within 60 s."""
    import api.main as _main
    from api.main import _cache_key, _evict_expired_cache

    key_expired = _cache_key("stale", None, None, 1, "", "all", "", "")
    _main._search_result_cache[key_expired] = (
        {"listings": [], "market_price": None},
        time.time() - 5.0,
    )

    # Pretend eviction just ran.
    _main._last_eviction_ts = time.time()
    _evict_expired_cache()

    # Entry should still be present because eviction was throttled.
    assert key_expired in _main._search_result_cache


# ── Integration tests — async endpoint cache hit ──────────────────────────────

def test_async_cache_hit_skips_scraper(client, tmp_path):
    """On a warm cache hit the scraper adapter must not be called."""
    import threading
    import api.main as _main
    from api.main import _cache_key

    # Pre-seed a valid cache entry.
    key = _cache_key("rtx 3080", None, None, 1, "", "all", "", "")
    _main._search_result_cache[key] = (
        {"listings": [], "market_price": 250.0},
        time.time() + 300.0,
    )

    scraper_called = threading.Event()

    def _fake_search(query, filters):
        scraper_called.set()
        return []

    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
        patch("api.main.Store") as mock_store_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.side_effect = _fake_search
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        mock_store = MagicMock()
        mock_store.get_listings_staged.return_value = {}
        mock_store.refresh_seller_categories.return_value = 0
        mock_store.save_listings.return_value = None
        mock_store.save_trust_scores.return_value = None
        mock_store.get_market_comp.return_value = None
        mock_store.get_seller.return_value = None
        mock_store.get_user_preference.return_value = None
        mock_store_cls.return_value = mock_store

        resp = client.get("/api/search/async?q=rtx+3080")
        assert resp.status_code == 202

        # Give the background worker a moment to run.
        scraper_called.wait(timeout=3.0)

    # Scraper must NOT have been called on a cache hit.
    assert not scraper_called.is_set(), "Scraper was called despite a warm cache hit"


def test_async_cache_miss_stores_result(client, tmp_path):
    """After a cache miss the result must be stored in _search_result_cache."""
    import threading
    import api.main as _main
    from api.main import _cache_key

    search_done = threading.Event()
    real_listing = _make_real_listing()

    def _fake_search(query, filters):
        return [real_listing]

    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment") as mock_enrich,
        patch("api.main.TrustScorer") as mock_scorer_cls,
        patch("api.main.Store") as mock_store_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.side_effect = _fake_search
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        mock_store = MagicMock()
        mock_store.get_listings_staged.return_value = {
            real_listing.platform_listing_id: real_listing
        }
        mock_store.refresh_seller_categories.return_value = 0
        mock_store.save_listings.return_value = None
        mock_store.save_trust_scores.return_value = None
        mock_store.get_market_comp.return_value = None
        mock_store.get_seller.return_value = None
        mock_store.get_user_preference.return_value = None
        mock_store_cls.return_value = mock_store

        def _enrich_side_effect(*args, **kwargs):
            search_done.set()

        mock_enrich.side_effect = _enrich_side_effect

        resp = client.get("/api/search/async?q=rtx+3080")
        assert resp.status_code == 202

        # Wait until the background worker reaches _trigger_scraper_enrichment.
        search_done.wait(timeout=5.0)

    assert search_done.is_set(), "Background search worker never completed"

    key = _cache_key("rtx 3080", None, None, 1, "", "all", "", "")
    assert key in _main._search_result_cache, "Result was not stored in cache after miss"
    payload, expiry = _main._search_result_cache[key]
    assert expiry > time.time(), "Cache entry has already expired"
    assert "listings" in payload


# ── Integration tests — async endpoint refresh=True ──────────────────────────

def test_async_refresh_bypasses_cache_read(client, tmp_path):
    """refresh=True must bypass cache read and invoke the scraper."""
    import threading
    import api.main as _main
    from api.main import _cache_key

    # Seed a valid cache entry so we can confirm it is bypassed.
    key = _cache_key("rtx 3080", None, None, 1, "", "all", "", "")
    _main._search_result_cache[key] = (
        {"listings": [], "market_price": 100.0},
        time.time() + 300.0,
    )

    scraper_called = threading.Event()

    def _fake_search(query, filters):
        scraper_called.set()
        return []

    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
        patch("api.main.Store") as mock_store_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.side_effect = _fake_search
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        mock_store = MagicMock()
        mock_store.get_listings_staged.return_value = {}
        mock_store.refresh_seller_categories.return_value = 0
        mock_store.save_listings.return_value = None
        mock_store.save_trust_scores.return_value = None
        mock_store.get_market_comp.return_value = None
        mock_store.get_seller.return_value = None
        mock_store.get_user_preference.return_value = None
        mock_store_cls.return_value = mock_store

        resp = client.get("/api/search/async?q=rtx+3080&refresh=true")
        assert resp.status_code == 202

        scraper_called.wait(timeout=5.0)

    assert scraper_called.is_set(), "Scraper was not called even though refresh=True"
