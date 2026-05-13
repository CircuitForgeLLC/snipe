"""Unit tests for QueryTranslator — LLMRouter and cf-orch backends mocked at boundary."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.llm.query_translator import QueryTranslator, QueryTranslatorError, SearchParamsResponse, _parse_response


# ── _parse_response ───────────────────────────────────────────────────────────

def test_parse_response_happy_path():
    raw = json.dumps({
        "base_query": "RTX 3080",
        "must_include_mode": "groups",
        "must_include": "rtx|geforce, 3080",
        "must_exclude": "mining,for parts",
        "max_price": 300.0,
        "min_price": None,
        "condition": ["used"],
        "category_id": "27386",
        "explanation": "Searching for used RTX 3080 GPUs under $300.",
    })
    result = _parse_response(raw)
    assert result.base_query == "RTX 3080"
    assert result.must_include_mode == "groups"
    assert result.max_price == 300.0
    assert result.min_price is None
    assert result.condition == ["used"]
    assert result.category_id == "27386"
    assert "RTX 3080" in result.explanation


def test_parse_response_missing_optional_fields():
    raw = json.dumps({
        "base_query": "vintage camera",
        "must_include_mode": "all",
        "must_include": "",
        "must_exclude": "",
        "max_price": None,
        "min_price": None,
        "condition": [],
        "category_id": None,
        "explanation": "Searching for vintage cameras.",
    })
    result = _parse_response(raw)
    assert result.category_id is None
    assert result.max_price is None
    assert result.condition == []


def test_parse_response_invalid_json():
    with pytest.raises(QueryTranslatorError, match="unparseable"):
        _parse_response("this is not json {{{ garbage")


def test_parse_response_missing_required_field():
    # base_query is required — missing it should raise
    raw = json.dumps({
        "must_include_mode": "all",
        "must_include": "",
        "must_exclude": "",
        "max_price": None,
        "min_price": None,
        "condition": [],
        "category_id": None,
        "explanation": "oops",
    })
    with pytest.raises(QueryTranslatorError):
        _parse_response(raw)


# ── Fixtures ──────────────────────────────────────────────────────────────────

from app.platforms.ebay.categories import EbayCategoryCache
from circuitforge_core.db import get_connection, run_migrations


@pytest.fixture
def db_with_categories(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn, Path("app/db/migrations"))
    cache = EbayCategoryCache(conn)
    cache._seed_bootstrap()
    return conn


_VALID_LLM_RESPONSE = json.dumps({
    "base_query": "RTX 3080",
    "must_include_mode": "groups",
    "must_include": "rtx|geforce, 3080",
    "must_exclude": "mining,for parts",
    "max_price": 300.0,
    "min_price": None,
    "condition": ["used"],
    "category_id": "27386",
    "explanation": "Searching for used RTX 3080 GPUs under $300.",
})


# ── Local LLMRouter backend ───────────────────────────────────────────────────

def _make_local_translator(db_conn, llm_response: str) -> QueryTranslator:
    from app.platforms.ebay.categories import EbayCategoryCache
    cache = EbayCategoryCache(db_conn)
    mock_router = MagicMock()
    mock_router.complete.return_value = llm_response
    return QueryTranslator(category_cache=cache, llm_router=mock_router)


def test_translate_returns_search_params(db_with_categories):
    t = _make_local_translator(db_with_categories, _VALID_LLM_RESPONSE)
    result = t.translate("used RTX 3080 under $300 no mining")
    assert result.base_query == "RTX 3080"
    assert result.max_price == 300.0


def test_translate_injects_category_hints(db_with_categories):
    """The system prompt sent to the LLM must contain category_id hints."""
    t = _make_local_translator(db_with_categories, _VALID_LLM_RESPONSE)
    t.translate("GPU")
    call_args = t._llm_router.complete.call_args
    system_prompt = call_args.kwargs.get("system") or call_args.args[1]
    # Bootstrap seeds "27386" for Graphics Cards — should appear in the prompt
    assert "27386" in system_prompt


def test_translate_empty_category_cache_still_works(tmp_path):
    """No crash when category cache is empty — prompt uses fallback text."""
    from circuitforge_core.db import get_connection, run_migrations
    conn = get_connection(tmp_path / "empty.db")
    run_migrations(conn, Path("app/db/migrations"))
    # Do NOT seed bootstrap — empty cache
    t = _make_local_translator(conn, json.dumps({
        "base_query": "vinyl",
        "must_include_mode": "all",
        "must_include": "",
        "must_exclude": "",
        "max_price": None,
        "min_price": None,
        "condition": [],
        "category_id": None,
        "explanation": "Searching for vinyl records.",
    }))
    result = t.translate("vinyl records")
    assert result.base_query == "vinyl"
    call_args = t._llm_router.complete.call_args
    system_prompt = call_args.kwargs.get("system") or call_args.args[1]
    assert "If none match" in system_prompt


def test_translate_llm_error_raises_query_translator_error(db_with_categories):
    from app.platforms.ebay.categories import EbayCategoryCache
    cache = EbayCategoryCache(db_with_categories)
    mock_router = MagicMock()
    mock_router.complete.side_effect = RuntimeError("all backends exhausted")
    t = QueryTranslator(category_cache=cache, llm_router=mock_router)
    with pytest.raises(QueryTranslatorError, match="LLM backend"):
        t.translate("used GPU")


# ── cf-orch backend ───────────────────────────────────────────────────────────

def _make_orch_translator(db_conn) -> QueryTranslator:
    from app.platforms.ebay.categories import EbayCategoryCache
    cache = EbayCategoryCache(db_conn)
    return QueryTranslator(category_cache=cache, cforch_url="http://orch.local:8700")


def _mock_alloc_response() -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "url": "http://cf-text.local:11434",
        "allocation_id": "alloc-abc123",
        "node_id": "heimdall",
    }
    resp.raise_for_status.return_value = None
    return resp


def _mock_chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    resp.raise_for_status.return_value = None
    return resp


def _mock_delete_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


def test_orch_translate_returns_search_params(db_with_categories):
    t = _make_orch_translator(db_with_categories)
    with patch("httpx.post") as mock_post, patch("httpx.delete") as mock_delete:
        mock_post.side_effect = [
            _mock_alloc_response(),
            _mock_chat_response(_VALID_LLM_RESPONSE),
        ]
        mock_delete.return_value = _mock_delete_response()
        result = t.translate("used RTX 3080 under $300")
    assert result.base_query == "RTX 3080"
    assert result.max_price == 300.0


def test_orch_allocates_with_correct_task_tag(db_with_categories):
    t = _make_orch_translator(db_with_categories)
    with patch("httpx.post") as mock_post, patch("httpx.delete"):
        mock_post.side_effect = [
            _mock_alloc_response(),
            _mock_chat_response(_VALID_LLM_RESPONSE),
        ]
        t.translate("GPU")
    alloc_call = mock_post.call_args_list[0]
    assert alloc_call.args[0] == "http://orch.local:8700/api/inference/task"
    body = alloc_call.kwargs.get("json") or alloc_call.args[1]
    assert body == {"product": "snipe", "task": "query_translation"}


def test_orch_releases_allocation_after_success(db_with_categories):
    t = _make_orch_translator(db_with_categories)
    with patch("httpx.post") as mock_post, patch("httpx.delete") as mock_delete:
        mock_post.side_effect = [
            _mock_alloc_response(),
            _mock_chat_response(_VALID_LLM_RESPONSE),
        ]
        mock_delete.return_value = _mock_delete_response()
        t.translate("GPU")
    mock_delete.assert_called_once()
    delete_url = mock_delete.call_args.args[0]
    assert "alloc-abc123" in delete_url


def test_orch_releases_allocation_on_inference_failure(db_with_categories):
    """Allocation must be released even when the inference call fails."""
    t = _make_orch_translator(db_with_categories)
    with patch("httpx.post") as mock_post, patch("httpx.delete") as mock_delete:
        mock_post.side_effect = [
            _mock_alloc_response(),
            Exception("inference timeout"),
        ]
        mock_delete.return_value = _mock_delete_response()
        with pytest.raises(QueryTranslatorError, match="LLM backend"):
            t.translate("GPU")
    mock_delete.assert_called_once()


def test_init_requires_at_least_one_backend(tmp_path):
    from circuitforge_core.db import get_connection, run_migrations
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn, Path("app/db/migrations"))
    cache = EbayCategoryCache(conn)
    with pytest.raises(ValueError, match="cforch_url or llm_router"):
        QueryTranslator(category_cache=cache)
