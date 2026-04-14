"""Unit tests for QueryTranslator — LLMRouter mocked at boundary."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.llm.query_translator import QueryTranslatorError, SearchParamsResponse, _parse_response


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
