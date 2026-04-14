"""Unit tests for EbayCategoryCache."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
