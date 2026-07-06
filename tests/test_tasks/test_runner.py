"""Tests for snipe background task runner."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_cforch_available = importlib.util.find_spec("circuitforge_orch") is not None
requires_cforch = pytest.mark.skipif(
    not _cforch_available,
    reason="circuitforge_orch not installed",
)

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
            stage      TEXT,
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


_VISION_JSON = json.dumps({
    "is_stock_photo": False,
    "visible_damage": False,
    "authenticity_signal": "genuine_product_photo",
    "confidence": "high",
})

_PARAMS = json.dumps({
    "photo_url": "https://example.com/photo.jpg",
    "listing_title": "Used iPhone 13",
})


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


# ── Local LLMRouter path ──────────────────────────────────────────────────────

def test_run_task_photo_analysis_local_success(tmp_db: Path):
    """Local path: vision result is written to trust_scores.photo_analysis_json."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    with patch("app.tasks.runner.requests") as mock_req, \
         patch("app.tasks.runner._assess_via_local_llm", return_value=_VISION_JSON):
        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

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
    assert parsed["confidence"] == "high"


def test_run_task_photo_fetch_failure_marks_failed(tmp_db: Path):
    """If photo download fails, task is marked failed without crashing."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    with patch("app.tasks.runner.requests") as mock_req:
        mock_req.get.side_effect = ConnectionError("fetch failed")
        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

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


# ── cf-orch path ──────────────────────────────────────────────────────────────

def _make_orch_client_mock(vision_json: str) -> MagicMock:
    """Build a CFOrchClient mock whose task_allocate context manager returns an Allocation."""
    alloc = MagicMock()
    alloc.url = "http://cf-vlm.local:8000"
    alloc.model = "bartowski--qwen2-vl-7b-instruct-gguf"

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=alloc)
    cm.__exit__ = MagicMock(return_value=False)

    client = MagicMock()
    client.task_allocate.return_value = cm
    return client


@requires_cforch
def test_run_task_photo_analysis_orch_success(tmp_db: Path):
    """Cloud path: CFOrchClient.task_allocate is used when GPU_SERVER_URL is set."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    chat_resp = MagicMock()
    chat_resp.json.return_value = {"choices": [{"message": {"content": _VISION_JSON}}]}
    chat_resp.raise_for_status = MagicMock()

    with patch("app.tasks.runner.requests") as mock_req, \
         patch.dict("os.environ", {"GPU_SERVER_URL": "http://cf-orch.local:8700"}), \
         patch("app.tasks.runner.httpx") as mock_httpx, \
         patch("circuitforge_orch.client.CFOrchClient") as MockClient:

        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        mock_httpx.post.return_value = chat_resp

        client_instance = _make_orch_client_mock(_VISION_JSON)
        MockClient.return_value = client_instance

        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

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
    assert parsed["authenticity_signal"] == "genuine_product_photo"


@requires_cforch
def test_run_task_photo_analysis_orch_uses_image_assessment_task(tmp_db: Path):
    """task_allocate must be called with product='snipe', task='image_assessment'."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    chat_resp = MagicMock()
    chat_resp.json.return_value = {"choices": [{"message": {"content": _VISION_JSON}}]}
    chat_resp.raise_for_status = MagicMock()

    with patch("app.tasks.runner.requests") as mock_req, \
         patch.dict("os.environ", {"GPU_SERVER_URL": "http://cf-orch.local:8700"}), \
         patch("app.tasks.runner.httpx") as mock_httpx, \
         patch("circuitforge_orch.client.CFOrchClient") as MockClient:

        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        mock_httpx.post.return_value = chat_resp

        client_instance = _make_orch_client_mock(_VISION_JSON)
        MockClient.return_value = client_instance

        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

    client_instance.task_allocate.assert_called_once_with("snipe", "image_assessment")


@requires_cforch
def test_run_task_photo_analysis_orch_sends_image_url_content(tmp_db: Path):
    """Vision payload must include image_url content block with data URI."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    captured_body: dict = {}

    def capture_post(url, **kwargs):
        nonlocal captured_body
        if "/v1/chat/completions" in url:
            captured_body = kwargs.get("json", {})
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": _VISION_JSON}}]}
        resp.raise_for_status = MagicMock()
        return resp

    with patch("app.tasks.runner.requests") as mock_req, \
         patch.dict("os.environ", {"GPU_SERVER_URL": "http://cf-orch.local:8700"}), \
         patch("app.tasks.runner.httpx") as mock_httpx, \
         patch("circuitforge_orch.client.CFOrchClient") as MockClient:

        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        mock_httpx.post.side_effect = capture_post

        client_instance = _make_orch_client_mock(_VISION_JSON)
        MockClient.return_value = client_instance

        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

    user_content = captured_body["messages"][1]["content"]
    image_blocks = [b for b in user_content if b.get("type") == "image_url"]
    assert image_blocks, "No image_url content block found in vision payload"
    url = image_blocks[0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,"), f"Unexpected image URL format: {url[:40]}"


@requires_cforch
def test_run_task_photo_analysis_orch_task_not_found_falls_back(tmp_db: Path):
    """TaskNotFound from cf-orch → graceful fallback to local LLMRouter."""
    from circuitforge_orch.client import TaskNotFound

    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    cm = MagicMock()
    cm.__enter__ = MagicMock(side_effect=TaskNotFound("snipe", "image_assessment"))
    cm.__exit__ = MagicMock(return_value=False)

    client_instance = MagicMock()
    client_instance.task_allocate.return_value = cm

    with patch("app.tasks.runner.requests") as mock_req, \
         patch.dict("os.environ", {"GPU_SERVER_URL": "http://cf-orch.local:8700"}), \
         patch("circuitforge_orch.client.CFOrchClient", return_value=client_instance), \
         patch("app.tasks.runner._assess_via_local_llm", return_value=_VISION_JSON) as mock_local:

        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None

        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

    mock_local.assert_called_once()

    conn = sqlite3.connect(tmp_db)
    task_row = conn.execute(
        "SELECT status FROM background_tasks WHERE id=?", (task_id,)
    ).fetchone()
    conn.close()
    assert task_row[0] == "completed"


def test_run_task_photo_analysis_non_json_response_writes_raw(tmp_db: Path):
    """Non-JSON LLM response is stored with parse_error flag rather than crashing."""
    task_id, _ = insert_task(tmp_db, "trust_photo_analysis", job_id=1, params=_PARAMS)

    with patch("app.tasks.runner.requests") as mock_req, \
         patch("app.tasks.runner._assess_via_local_llm", return_value="not valid json at all"):
        mock_req.get.return_value.content = b"fake_image_bytes"
        mock_req.get.return_value.raise_for_status = lambda: None
        run_task(tmp_db, task_id, "trust_photo_analysis", 1, _PARAMS)

    conn = sqlite3.connect(tmp_db)
    score_row = conn.execute(
        "SELECT photo_analysis_json FROM trust_scores WHERE listing_id=1"
    ).fetchone()
    conn.close()
    parsed = json.loads(score_row[0])
    assert parsed.get("parse_error") is True
    assert "raw_response" in parsed
