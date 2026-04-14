"""Unit tests for QueryTranslator — LLMRouter mocked at boundary."""
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


# ── QueryTranslator (integration with mocked LLMRouter) ──────────────────────

from app.platforms.ebay.categories import EbayCategoryCache
from circuitforge_core.db import get_connection, run_migrations


@pytest.fixture
def db_with_categories(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    run_migrations(conn, Path("app/db/migrations"))
    cache = EbayCategoryCache(conn)
    cache._seed_bootstrap()
    return conn


def _make_translator(db_conn, llm_response: str) -> QueryTranslator:
    from app.platforms.ebay.categories import EbayCategoryCache
    cache = EbayCategoryCache(db_conn)
    mock_router = MagicMock()
    mock_router.complete.return_value = llm_response
    return QueryTranslator(category_cache=cache, llm_router=mock_router)


def test_translate_returns_search_params(db_with_categories):
    llm_out = json.dumps({
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
    t = _make_translator(db_with_categories, llm_out)
    result = t.translate("used RTX 3080 under $300 no mining")
    assert result.base_query == "RTX 3080"
    assert result.max_price == 300.0


def test_translate_injects_category_hints(db_with_categories):
    """The system prompt sent to the LLM must contain category_id hints."""
    llm_out = json.dumps({
        "base_query": "GPU",
        "must_include_mode": "all",
        "must_include": "",
        "must_exclude": "",
        "max_price": None,
        "min_price": None,
        "condition": [],
        "category_id": None,
        "explanation": "Searching for GPUs.",
    })
    t = _make_translator(db_with_categories, llm_out)
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
    llm_out = json.dumps({
        "base_query": "vinyl",
        "must_include_mode": "all",
        "must_include": "",
        "must_exclude": "",
        "max_price": None,
        "min_price": None,
        "condition": [],
        "category_id": None,
        "explanation": "Searching for vinyl records.",
    })
    t = _make_translator(conn, llm_out)
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
