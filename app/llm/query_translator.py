# app/llm/query_translator.py
# BSL 1.1 License
"""LLM query builder — translates natural language to eBay SearchFilters.

Supports two backends, selected at construction time:

  cforch_url  — cf-orch task endpoint (cloud/premium). The coordinator resolves
                product+task to a model and returns an allocation. The caller
                POSTs to the allocated service URL, then DELETEs the allocation.

  llm_router  — circuitforge_core.LLMRouter (local installs: ollama/vllm/api keys).

Exactly one of cforch_url or llm_router must be supplied.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from app.platforms.ebay.categories import EbayCategoryCache

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


# ── System prompt template ────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are a search assistant for Snipe, an eBay listing intelligence tool.
Your job is to translate a natural-language description of what someone is looking for
into a structured eBay search configuration.

Return ONLY a JSON object with these exact fields — no preamble, no markdown, no extra keys:
  base_query        (string)  Primary search term, short — e.g. "RTX 3080", "vintage Leica"
  must_include_mode (string)  One of: "all" (AND), "any" (OR), "groups" (CNF: pipe=OR within group, comma=AND between groups)
  must_include      (string)  Filter string per mode — leave blank if nothing to filter
  must_exclude      (string)  Comma-separated terms to exclude — e.g. "mining,for parts,broken"
  max_price         (number|null)  Maximum price in USD, or null
  min_price         (number|null)  Minimum price in USD, or null
  condition         (array)   Any of: "new", "used", "for_parts" — empty array means any condition
  category_id       (string|null)  eBay category ID from the list below, or null if no match
  explanation       (string)  One plain sentence summarizing what you built

eBay "groups" mode syntax example: to find a GPU that is BOTH (nvidia OR amd) AND (16gb OR 8gb):
  must_include_mode: "groups"
  must_include: "nvidia|amd, 16gb|8gb"

Phrase "like new", "open box", "refurbished" -> condition: ["used"]
Phrase "broken", "for parts", "not working" -> condition: ["for_parts"]
If unsure about condition, use an empty array.

Available eBay categories (use category_id verbatim if one fits — otherwise omit):
{category_hints}

If none match, omit category_id (set to null). Respond with valid JSON only. No commentary outside the JSON object.
"""


# ── QueryTranslator ───────────────────────────────────────────────────────────

class QueryTranslator:
    """Translates natural-language search descriptions into SearchParamsResponse.

    Args:
        category_cache: An EbayCategoryCache instance (may have empty cache).
        cforch_url: cf-orch coordinator base URL (cloud/premium path).
        llm_router: A circuitforge_core LLMRouter instance (local path).

    Exactly one of cforch_url or llm_router must be provided.
    """

    def __init__(
        self,
        category_cache: "EbayCategoryCache",
        *,
        cforch_url: str | None = None,
        llm_router: object | None = None,
    ) -> None:
        if cforch_url is None and llm_router is None:
            raise ValueError("Either cforch_url or llm_router must be provided")
        self._cache = category_cache
        self._cforch_url = cforch_url
        self._llm_router = llm_router

    def translate(self, natural_language: str) -> SearchParamsResponse:
        """Translate a natural-language query into a SearchParamsResponse.

        Raises QueryTranslatorError if the LLM fails or returns bad JSON.
        """
        # Extract up to 10 keywords for category hint lookup
        keywords = [w for w in natural_language.split()[:10] if len(w) > 2]
        hints = self._cache.get_relevant(keywords, limit=30)
        if not hints:
            hints = self._cache.get_all_for_prompt(limit=40)

        if hints:
            category_hints = "\n".join(f"{cid}: {path}" for cid, path in hints)
        else:
            category_hints = "(no categories cached — omit category_id)"

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(category_hints=category_hints)

        try:
            if self._cforch_url:
                raw = self._call_orch(system_prompt, natural_language)
            else:
                raw = self._call_local(system_prompt, natural_language)
        except QueryTranslatorError:
            raise
        except Exception as exc:
            raise QueryTranslatorError(
                f"LLM backend error: {exc}", raw=""
            ) from exc

        return _parse_response(raw)

    def _call_orch(self, system_prompt: str, user_message: str) -> str:
        """Allocate via cf-orch task endpoint, call the model, release the slot."""
        alloc_resp = httpx.post(
            f"{self._cforch_url}/api/inference/task",
            json={"product": "snipe", "task": "query_translation"},
            timeout=10.0,
        )
        alloc_resp.raise_for_status()
        alloc = alloc_resp.json()
        service_url = alloc["url"]
        allocation_id = alloc["allocation_id"]
        try:
            resp = httpx.post(
                f"{service_url}/v1/chat/completions",
                json={
                    "model": "__auto__",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": 512,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        finally:
            try:
                httpx.delete(
                    f"{self._cforch_url}/api/services/cf-text/allocations/{allocation_id}",
                    timeout=5.0,
                )
            except Exception:
                log.warning("Failed to release cf-orch allocation %s", allocation_id)

    def _call_local(self, system_prompt: str, user_message: str) -> str:
        """Call the locally-configured LLMRouter (ollama/vllm/api keys)."""
        return self._llm_router.complete(  # type: ignore[union-attr]
            user_message,
            system=system_prompt,
            max_tokens=512,
        )
