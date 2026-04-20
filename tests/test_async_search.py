"""Tests for GET /api/search/async (fire-and-forget search + SSE streaming).

Verifies:
  - Returns HTTP 202 with session_id and status: "queued"
  - session_id is registered in _update_queues immediately
  - Actual scraping is not performed (mocked out)
  - Empty query path returns a completed session with done event
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path):
    """TestClient with a fresh tmp DB.  Must set SNIPE_DB *before* importing app."""
    os.environ["SNIPE_DB"] = str(tmp_path / "snipe.db")
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


def _make_mock_listing():
    """Return a minimal mock listing object that satisfies the search pipeline."""
    m = MagicMock()
    m.platform_listing_id = "123456789"
    m.seller_platform_id = "test_seller"
    m.title = "Test GPU"
    m.price = 100.0
    m.currency = "USD"
    m.condition = "Used"
    m.url = "https://www.ebay.com/itm/123456789"
    m.photo_urls = []
    m.listing_age_days = 5
    m.buying_format = "fixed_price"
    m.ends_at = None
    m.fetched_at = None
    m.trust_score_id = None
    m.id = 1
    m.category_name = None
    return m


# ── Core contract tests ───────────────────────────────────────────────────────

def test_async_search_returns_202(client):
    """GET /api/search/async?q=... returns HTTP 202 with session_id and status."""
    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.return_value = []
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        resp = client.get("/api/search/async?q=test+gpu")

    assert resp.status_code == 202
    data = resp.json()
    assert "session_id" in data
    assert data["status"] == "queued"
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_async_search_registers_session_id(client):
    """session_id returned by 202 response must appear in _update_queues immediately."""
    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.return_value = []
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        resp = client.get("/api/search/async?q=test+gpu")

    assert resp.status_code == 202
    session_id = resp.json()["session_id"]

    # The queue must be registered so the SSE endpoint can open it.
    from api.main import _update_queues
    assert session_id in _update_queues


def test_async_search_empty_query(client):
    """Empty query returns 202 with a pre-loaded done sentinel, no scraping needed."""
    resp = client.get("/api/search/async?q=")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "session_id" in data

    from api.main import _update_queues
    import queue as _queue
    sid = data["session_id"]
    assert sid in _update_queues
    q = _update_queues[sid]
    # First item should be the empty listings event
    first = q.get_nowait()
    assert first is not None
    assert first["type"] == "listings"
    assert first["listings"] == []
    # Second item should be the sentinel
    sentinel = q.get_nowait()
    assert sentinel is None


def test_async_search_no_real_chromium(client):
    """Async search endpoint must not launch real Chromium in tests.

    Verifies that the background scraper is submitted to the executor but the
    adapter factory is patched — no real Playwright/Xvfb process is spawned.
    Uses a broad patch on Store to avoid sqlite3 DB path issues in the thread pool.
    """
    import threading
    scrape_called = threading.Event()

    def _fake_search(query, filters):
        scrape_called.set()
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
    # Give the background worker a moment to run (it's in a thread pool)
    scrape_called.wait(timeout=5.0)
    # If we get here without a real Playwright process, the test passes.
    assert scrape_called.is_set(), "Background search worker never ran"


def test_async_search_query_params_forwarded(client):
    """All filter params accepted by /api/search are also accepted here."""
    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.return_value = []
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        resp = client.get(
            "/api/search/async"
            "?q=rtx+3080"
            "&max_price=400"
            "&min_price=100"
            "&pages=2"
            "&must_include=rtx,3080"
            "&must_include_mode=all"
            "&must_exclude=mining"
            "&category_id=27386"
            "&adapter=auto"
        )

    assert resp.status_code == 202


def test_async_search_session_id_is_uuid(client):
    """session_id must be a valid UUID v4 string."""
    import uuid as _uuid

    with (
        patch("api.main._make_adapter") as mock_adapter_factory,
        patch("api.main._trigger_scraper_enrichment"),
        patch("api.main.TrustScorer") as mock_scorer_cls,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search.return_value = []
        mock_adapter.get_completed_sales.return_value = None
        mock_adapter_factory.return_value = mock_adapter

        mock_scorer = MagicMock()
        mock_scorer.score_batch.return_value = []
        mock_scorer_cls.return_value = mock_scorer

        resp = client.get("/api/search/async?q=test")

    assert resp.status_code == 202
    sid = resp.json()["session_id"]
    # Should not raise if it's a valid UUID
    parsed = _uuid.UUID(sid)
    assert str(parsed) == sid
