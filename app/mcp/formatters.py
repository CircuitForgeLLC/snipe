"""Condense Snipe API search results into LLM-friendly format.

Raw Snipe responses are verbose — full listing dicts, nested seller objects,
redundant fields. This module trims to what an LLM needs for reasoning:
title, price, market delta, trust summary, GPU inference score, url.

Results are sorted by a composite key: trust × gpu_inference_score / price.
This surfaces high-trust, VRAM-rich, underpriced boards at the top.
"""
from __future__ import annotations

import json
from typing import Any

from app.mcp.gpu_scoring import parse_gpu, score_gpu


def format_results(
    response: dict[str, Any],
    vram_weight: float = 0.6,
    arch_weight: float = 0.4,
    top_n: int = 20,
) -> dict[str, Any]:
    """Return a condensed, LLM-ready summary of a Snipe search response."""
    listings: list[dict] = response.get("listings", [])
    trust_map: dict = response.get("trust_scores", {})
    seller_map: dict = response.get("sellers", {})
    market_price: float | None = response.get("market_price")

    condensed = []
    for listing in listings:
        lid = listing.get("platform_listing_id", "")
        title = listing.get("title", "")
        price = float(listing.get("price") or 0)
        trust = trust_map.get(lid, {})
        seller_id = listing.get("seller_platform_id", "")
        seller = seller_map.get(seller_id, {})

        gpu_info = _gpu_info(title, vram_weight, arch_weight)
        trust_score = trust.get("composite_score", 0) or 0
        inference_score = gpu_info["inference_score"] if gpu_info else 0.0

        condensed.append({
            "id": lid,
            "title": title,
            "price": price,
            "vs_market": _vs_market(price, market_price),
            "trust_score": trust_score,
            "trust_partial": bool(trust.get("score_is_partial")),
            "red_flags": _parse_flags(trust.get("red_flags_json", "[]")),
            "seller_age_days": seller.get("account_age_days"),
            "seller_feedback": seller.get("feedback_count"),
            "gpu": gpu_info,
            "url": listing.get("url", ""),
            # Sort key — not included in output
            "_sort_key": _composite_key(trust_score, inference_score, price),
        })

    condensed.sort(key=lambda r: r["_sort_key"], reverse=True)
    for r in condensed:
        del r["_sort_key"]

    no_gpu = sum(1 for r in condensed if r["gpu"] is None)
    return {
        "total_found": len(listings),
        "showing": min(top_n, len(condensed)),
        "market_price": market_price,
        "adapter": response.get("adapter_used"),
        "no_gpu_detected": no_gpu,
        "results": condensed[:top_n],
    }


def _gpu_info(title: str, vram_weight: float, arch_weight: float) -> dict | None:
    spec = parse_gpu(title)
    if not spec:
        return None
    match = score_gpu(spec, vram_weight, arch_weight)
    return {
        "model": spec.model,
        "vram_gb": spec.vram_gb,
        "arch": spec.arch_name,
        "vendor": spec.vendor,
        "vram_score": match.vram_score,
        "arch_score": match.arch_score,
        "inference_score": match.inference_score,
    }


def _vs_market(price: float, market_price: float | None) -> str | None:
    if not market_price or price <= 0:
        return None
    delta_pct = ((market_price - price) / market_price) * 100
    if delta_pct >= 0:
        return f"{delta_pct:.0f}% below market (${market_price:.0f} median)"
    return f"{abs(delta_pct):.0f}% above market (${market_price:.0f} median)"


def _composite_key(trust_score: float, inference_score: float, price: float) -> float:
    """Higher = better value. Zero price or zero trust scores near zero."""
    if price <= 0 or trust_score <= 0:
        return 0.0
    return (trust_score * (inference_score or 50.0)) / price


def _parse_flags(flags_json: str) -> list[str]:
    try:
        return json.loads(flags_json) or []
    except (ValueError, TypeError):
        return []
