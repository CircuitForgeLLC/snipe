# app/llm/query_translator.py
# BSL 1.1 License
"""LLM query builder — translates natural language to eBay SearchFilters.

The QueryTranslator calls LLMRouter.complete() (synchronous) with a domain-aware
system prompt. The prompt includes category hints injected from EbayCategoryCache.
The LLM returns a single JSON object matching SearchParamsResponse.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


class QueryTranslatorError(Exception):
    """Raised when the LLM output cannot be parsed into SearchParamsResponse."""
    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


@dataclass(frozen=True)
class SearchParamsResponse:
    """Parsed LLM response — maps 1:1 to the /api/search query parameters."""
    base_query: str
    must_include_mode: str       # "all" | "any" | "groups"
    must_include: str            # raw filter string
    must_exclude: str            # comma-separated exclusion terms
    max_price: Optional[float]
    min_price: Optional[float]
    condition: list[str]         # subset of ["new", "used", "for_parts"]
    category_id: Optional[str]   # eBay category ID string, or None
    explanation: str             # one-sentence plain-language summary


_VALID_MODES = {"all", "any", "groups"}
_VALID_CONDITIONS = {"new", "used", "for_parts"}


def _parse_response(raw: str) -> SearchParamsResponse:
    """Parse the LLM's raw text output into a SearchParamsResponse.

    Raises QueryTranslatorError if the JSON is malformed or required fields
    are missing.
    """
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise QueryTranslatorError(f"LLM returned unparseable JSON: {exc}", raw=raw) from exc

    try:
        base_query = str(data["base_query"]).strip()
        if not base_query:
            raise KeyError("base_query is empty")
        must_include_mode = str(data.get("must_include_mode", "all"))
        if must_include_mode not in _VALID_MODES:
            must_include_mode = "all"
        must_include = str(data.get("must_include", ""))
        must_exclude = str(data.get("must_exclude", ""))
        max_price = float(data["max_price"]) if data.get("max_price") is not None else None
        min_price = float(data["min_price"]) if data.get("min_price") is not None else None
        raw_conditions = data.get("condition", [])
        condition = [c for c in raw_conditions if c in _VALID_CONDITIONS]
        category_id = str(data["category_id"]) if data.get("category_id") else None
        explanation = str(data.get("explanation", "")).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise QueryTranslatorError(
            f"LLM response missing or invalid field: {exc}", raw=raw
        ) from exc

    return SearchParamsResponse(
        base_query=base_query,
        must_include_mode=must_include_mode,
        must_include=must_include,
        must_exclude=must_exclude,
        max_price=max_price,
        min_price=min_price,
        condition=condition,
        category_id=category_id,
        explanation=explanation,
    )


class QueryTranslator:
    """Stub — implemented in Task 6."""
    pass
