"""Unit tests for EbayCategoryCache."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.platforms.ebay.categories import EbayCategoryCache

BOOTSTRAP_MIN = 10  # bootstrap must seed at least this many rows


@pytest.fixture
def db(tmp_path):
    """In-memory SQLite with migrations applied."""
    from circuitforge_core.db import get_connection, run_migrations
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn, Path("app/db/migrations"))
    return conn


def test_is_stale_empty_db(db):
    cache = EbayCategoryCache(db)
    assert cache.is_stale() is True


def test_is_stale_fresh(db):
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO ebay_categories (category_id, name, full_path, is_leaf, refreshed_at)"
        " VALUES (?, ?, ?, 1, ?)",
        ("12345", "Graphics Cards", "Consumer Electronics > GPUs > Graphics Cards", now),
    )
    db.commit()
    cache = EbayCategoryCache(db)
    assert cache.is_stale() is False


def test_is_stale_old(db):
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    db.execute(
        "INSERT INTO ebay_categories (category_id, name, full_path, is_leaf, refreshed_at)"
        " VALUES (?, ?, ?, 1, ?)",
        ("12345", "Graphics Cards", "Consumer Electronics > GPUs > Graphics Cards", old),
    )
    db.commit()
    cache = EbayCategoryCache(db)
    assert cache.is_stale() is True


def test_seed_bootstrap_populates_rows(db):
    cache = EbayCategoryCache(db)
    cache._seed_bootstrap()
    cur = db.execute("SELECT COUNT(*) FROM ebay_categories")
    count = cur.fetchone()[0]
    assert count >= BOOTSTRAP_MIN


def test_get_relevant_keyword_match(db):
    cache = EbayCategoryCache(db)
    cache._seed_bootstrap()
    results = cache.get_relevant(["GPU", "graphics"], limit=5)
    ids = [r[0] for r in results]
    assert "27386" in ids  # Graphics Cards


def test_get_relevant_no_match(db):
    cache = EbayCategoryCache(db)
    cache._seed_bootstrap()
    results = cache.get_relevant(["zzznomatch_xyzxyz"], limit=5)
    assert results == []


def test_get_relevant_respects_limit(db):
    cache = EbayCategoryCache(db)
    cache._seed_bootstrap()
    results = cache.get_relevant(["electronics"], limit=3)
    assert len(results) <= 3


def test_get_all_for_prompt_returns_rows(db):
    cache = EbayCategoryCache(db)
    cache._seed_bootstrap()
    results = cache.get_all_for_prompt(limit=10)
    assert len(results) > 0
    # Each entry is (category_id, full_path)
    assert all(len(r) == 2 for r in results)


def _make_tree_response() -> dict:
    """Minimal eBay Taxonomy API tree response with two leaf nodes."""
    return {
        "categoryTreeId": "0",
        "rootCategoryNode": {
            "category": {"categoryId": "6000", "categoryName": "Root"},
            "leafCategoryTreeNode": False,
            "childCategoryTreeNodes": [
                {
                    "category": {"categoryId": "6001", "categoryName": "Electronics"},
                    "leafCategoryTreeNode": False,
                    "childCategoryTreeNodes": [
                        {
                            "category": {"categoryId": "6002", "categoryName": "GPUs"},
                            "leafCategoryTreeNode": True,
                            "childCategoryTreeNodes": [],
                        },
                        {
                            "category": {"categoryId": "6003", "categoryName": "CPUs"},
                            "leafCategoryTreeNode": True,
                            "childCategoryTreeNodes": [],
                        },
                    ],
                }
            ],
        },
    }


def test_refresh_inserts_leaf_nodes(db):
    mock_tm = MagicMock()
    mock_tm.get_token.return_value = "fake-token"

    tree_resp = MagicMock()
    tree_resp.raise_for_status = MagicMock()
    tree_resp.json.return_value = _make_tree_response()

    id_resp = MagicMock()
    id_resp.raise_for_status = MagicMock()
    id_resp.json.return_value = {"categoryTreeId": "0"}

    with patch("app.platforms.ebay.categories.requests.get") as mock_get:
        mock_get.side_effect = [id_resp, tree_resp]
        cache = EbayCategoryCache(db)
        count = cache.refresh(mock_tm)

    assert count == 2  # two leaf nodes in our fake tree
    cur = db.execute("SELECT category_id FROM ebay_categories ORDER BY category_id")
    ids = {row[0] for row in cur.fetchall()}
    assert "6002" in ids
    assert "6003" in ids


def test_refresh_no_token_manager_seeds_bootstrap(db):
    cache = EbayCategoryCache(db)
    count = cache.refresh(token_manager=None)
    assert count >= BOOTSTRAP_MIN


def test_refresh_api_error_logs_warning(db, caplog):
    import logging
    mock_tm = MagicMock()
    mock_tm.get_token.return_value = "fake-token"

    with patch("app.platforms.ebay.categories.requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        cache = EbayCategoryCache(db)
        with caplog.at_level(logging.WARNING, logger="app.platforms.ebay.categories"):
            count = cache.refresh(mock_tm)

    # Falls back to bootstrap on API error
    assert count >= BOOTSTRAP_MIN
