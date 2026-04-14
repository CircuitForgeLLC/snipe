"""Integration tests for POST /api/search/build."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """TestClient with a fresh DB and mocked LLMRouter/category cache."""
    import os
    os.environ["SNIPE_DB"] = str(tmp_path / "snipe.db")
    # Import app AFTER setting SNIPE_DB so the DB path is picked up
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


def _good_llm_response() -> str:
    return json.dumps({
        "base_query": "RTX 3080",
        "must_include_mode": "groups",
        "must_include": "rtx|geforce, 3080",
        "must_exclude": "mining",
        "max_price": 300.0,
        "min_price": None,
        "condition": ["used"],
        "category_id": "27386",
        "explanation": "Used RTX 3080 under $300.",
    })


def test_build_endpoint_success(client):
    with patch("api.main._get_query_translator") as mock_get_t:
        mock_t = MagicMock()
        from app.llm.query_translator import SearchParamsResponse
        mock_t.translate.return_value = SearchParamsResponse(
            base_query="RTX 3080",
            must_include_mode="groups",
            must_include="rtx|geforce, 3080",
            must_exclude="mining",
            max_price=300.0,
            min_price=None,
            condition=["used"],
            category_id="27386",
            explanation="Used RTX 3080 under $300.",
        )
        mock_get_t.return_value = mock_t
        resp = client.post(
            "/api/search/build",
            json={"natural_language": "used RTX 3080 under $300 no mining"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_query"] == "RTX 3080"
    assert data["explanation"] == "Used RTX 3080 under $300."


def test_build_endpoint_llm_unavailable(client):
    with patch("api.main._get_query_translator") as mock_get_t:
        mock_get_t.return_value = None  # no translator configured
        resp = client.post(
            "/api/search/build",
            json={"natural_language": "GPU"},
        )
    assert resp.status_code == 503


def test_build_endpoint_bad_json(client):
    with patch("api.main._get_query_translator") as mock_get_t:
        from app.llm.query_translator import QueryTranslatorError
        mock_t = MagicMock()
        mock_t.translate.side_effect = QueryTranslatorError("unparseable", raw="garbage output")
        mock_get_t.return_value = mock_t
        resp = client.post(
            "/api/search/build",
            json={"natural_language": "GPU"},
        )
    assert resp.status_code == 422
    assert "raw" in resp.json()["detail"]
