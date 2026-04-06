"""Tests for the shared feedback router (circuitforge-core) mounted in snipe."""
from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from circuitforge_core.api.feedback import make_feedback_router


# ── Test app factory ──────────────────────────────────────────────────────────

def _make_client(demo_mode_fn: Callable[[], bool] | None = None) -> TestClient:
    app = FastAPI()
    router = make_feedback_router(
        repo="Circuit-Forge/snipe",
        product="snipe",
        demo_mode_fn=demo_mode_fn,
    )
    app.include_router(router, prefix="/api/feedback")
    return TestClient(app)


# ── GET /api/feedback/status ──────────────────────────────────────────────────

def test_status_disabled_when_no_token(monkeypatch):
    monkeypatch.delenv("FORGEJO_API_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    client = _make_client(demo_mode_fn=lambda: False)
    res = client.get("/api/feedback/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": False}


def test_status_enabled_when_token_set(monkeypatch):
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    client = _make_client(demo_mode_fn=lambda: False)
    res = client.get("/api/feedback/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": True}


def test_status_disabled_in_demo_mode(monkeypatch):
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    demo = True
    client = _make_client(demo_mode_fn=lambda: demo)
    res = client.get("/api/feedback/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": False}


# ── POST /api/feedback ────────────────────────────────────────────────────────

def test_submit_returns_503_when_no_token(monkeypatch):
    monkeypatch.delenv("FORGEJO_API_TOKEN", raising=False)
    client = _make_client(demo_mode_fn=lambda: False)
    res = client.post("/api/feedback", json={
        "title": "Test", "description": "desc", "type": "bug",
    })
    assert res.status_code == 503


def test_submit_returns_403_in_demo_mode(monkeypatch):
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")
    demo = True
    client = _make_client(demo_mode_fn=lambda: demo)
    res = client.post("/api/feedback", json={
        "title": "Test", "description": "desc", "type": "bug",
    })
    assert res.status_code == 403


def test_submit_creates_issue(monkeypatch):
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")

    label_response = MagicMock()
    label_response.ok = True
    label_response.json.return_value = [
        {"id": 1, "name": "beta-feedback"},
        {"id": 2, "name": "needs-triage"},
        {"id": 3, "name": "bug"},
    ]

    issue_response = MagicMock()
    issue_response.ok = True
    issue_response.json.return_value = {
        "number": 7,
        "html_url": "https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/7",
    }

    client = _make_client(demo_mode_fn=lambda: False)

    with patch("circuitforge_core.api.feedback.requests.get", return_value=label_response), \
         patch("circuitforge_core.api.feedback.requests.post", return_value=issue_response):
        res = client.post("/api/feedback", json={
            "title": "Listing scores wrong",
            "description": "Trust score shows 0 when seller has 1000 feedback",
            "type": "bug",
            "repro": "1. Search for anything\n2. Check trust score",
            "view": "search",
        })

    assert res.status_code == 200
    data = res.json()
    assert data["issue_number"] == 7
    assert data["issue_url"] == "https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/7"


def test_submit_returns_502_on_forgejo_error(monkeypatch):
    monkeypatch.setenv("FORGEJO_API_TOKEN", "test-token")

    label_response = MagicMock()
    label_response.ok = True
    label_response.json.return_value = [
        {"id": 1, "name": "beta-feedback"},
        {"id": 2, "name": "needs-triage"},
        {"id": 3, "name": "question"},
    ]

    bad_response = MagicMock()
    bad_response.ok = False
    bad_response.text = "internal server error"

    client = _make_client(demo_mode_fn=lambda: False)

    with patch("circuitforge_core.api.feedback.requests.get", return_value=label_response), \
         patch("circuitforge_core.api.feedback.requests.post", return_value=bad_response):
        res = client.post("/api/feedback", json={
            "title": "Oops", "description": "desc", "type": "other",
        })

    assert res.status_code == 502
