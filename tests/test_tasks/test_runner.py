"""Tests for snipe background task runner."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.runner import (
    LLM_TASK_TYPES,
    VRAM_BUDGETS,
    insert_task,
    run_task,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "snipe.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE background_tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type  TEXT    NOT NULL,
            job_id     INTEGER NOT NULL DEFAULT 0,
            status     TEXT    NOT NULL DEFAULT 'queued',
            params     TEXT,
            error      TEXT,
            created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE trust_scores (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id           INTEGER NOT NULL,
            composite_score      INTEGER NOT NULL DEFAULT 0,
            photo_analysis_json  TEXT,
            red_flags_json       TEXT    NOT NULL DEFAULT '[]',
            scored_at            TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO trust_scores (listing_id, composite_score) VALUES (1, 72);
    """)
    conn.commit()
    conn.close()
    return db


def test_llm_task_types_defined():
    assert "trust_photo_analysis" in LLM_TASK_TYPES


def test_vram_budgets_defined():
    assert "trust_photo_analysis" in VRAM_BUDGETS
    assert VRAM_BUDGETS["trust_photo_analysis"] > 0


def test_insert_task_creates_row(tmp_db: Path):
    task_id, is_new = insert_task(tmp_db, "trust_photo_analysis", job_id=1)
    assert is_new is True
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT status FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "queued"


def test_insert_task_dedup(tmp_db: Path):
    id1, new1 = insert_task(tmp_db, "trust_photo_analysis", job_id=1)
    id2, new2 = insert_task(tmp_db, "trust_photo_analysis", job_id=1)
    assert id1 == id2
    assert new1 is True
    assert new2 is False


def test_run_task_photo_analysis_success(tmp_db: Path):
    """Vision analysis result is written to trust_scores.photo_analysis_json."""
    params = json.dumps({
        "listing_id": 1,
        "photo_url": "https://example.com/photo.jpg",
        "listing_title": "Used iPhone 13",
    })
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=params)

    vision_result = {
        "is_stock_photo": False,
        "visible_damage": False,
        "authenticity_signal": "genuine_product_photo",
        "confidence": "high",
    }

    with patch("app.tasks.runner.requests") as mock_req, \
         patch("app.tasks.runner.LLMRouter") as MockRouter:
        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        instance = MockRouter.return_value
        instance.complete.return_value = json.dumps(vision_result)
        run_task(tmp_db, task_id, "trust_photo_analysis", 1, params)

    conn = sqlite3.connect(tmp_db)
    score_row = conn.execute(
        "SELECT photo_analysis_json FROM trust_scores WHERE listing_id=1"
    ).fetchone()
    task_row = conn.execute(
        "SELECT status FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert task_row[0] == "completed"
    parsed = json.loads(score_row[0])
    assert parsed["is_stock_photo"] is False


def test_run_task_photo_fetch_failure_marks_failed(tmp_db: Path):
    """If photo download fails, task is marked failed without crashing."""
    params = json.dumps({
        "listing_id": 1,
        "photo_url": "https://example.com/bad.jpg",
        "listing_title": "Laptop",
    })
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=params)

    with patch("app.tasks.runner.requests") as mock_req:
        mock_req.get.side_effect = ConnectionError("fetch failed")
        run_task(tmp_db, task_id, "trust_photo_analysis", 1, params)

    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT status, error FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert "fetch failed" in row[1]


def test_run_task_no_photo_url_marks_failed(tmp_db: Path):
    params = json.dumps({"listing_id": 1})
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=params)
    run_task(tmp_db, task_id, "trust_photo_analysis", 1, params)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT status, error FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert "photo_url" in row[1]


def test_run_task_unknown_type_marks_failed(tmp_db: Path):
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1)
    run_task(tmp_db, task_id, "unknown_type", 1, None)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT status FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "failed"
