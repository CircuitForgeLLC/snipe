"""Snipe MCP Server — eBay search with trust scoring and GPU inference-value ranking.

Exposes three tools to Claude:
  snipe_search  — search eBay via Snipe, GPU-scored and trust-ranked
  snipe_enrich  — deep seller/listing enrichment for a specific result
  snipe_save    — persist a productive search for ongoing monitoring

Run with:
  python -m app.mcp.server
  (from /Library/Development/CircuitForge/snipe with cf conda env active)

Configure in Claude Code ~/.claude.json:
  "snipe": {
    "command": "/devl/miniconda3/envs/cf/bin/python",
    "args": ["-m", "app.mcp.server"],
    "cwd": "/Library/Development/CircuitForge/snipe",
    "env": { "SNIPE_API_URL": "http://localhost:8510" }
  }
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_SNIPE_API = os.environ.get("SNIPE_API_URL", "http://localhost:8510")
_TIMEOUT = 120.0

server = Server("snipe")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="snipe_search",
            description=(
                "Search eBay listings via Snipe. Returns results condensed for LLM reasoning, "
                "sorted by composite value: trust_score × gpu_inference_score / price. "
                "GPU inference_score weights VRAM and architecture tier — tune with vram_weight/arch_weight. "
                "Use must_include_mode='groups' with pipe-separated OR alternatives for broad GPU coverage "
                "(e.g. 'rtx 3060|rtx 3070|rtx 3080'). "
                "Laptop Motherboard category ID: 177946."
            ),
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Base eBay search keywords, e.g. 'laptop motherboard'",
                    },
                    "must_include": {
                        "type": "string",
                        "description": (
                            "Comma-separated AND groups; use | for OR within a group. "
                            "E.g. 'rtx 3060|rtx 3070|rx 6700m, 8gb|12gb|16gb'"
                        ),
                    },
                    "must_include_mode": {
                        "type": "string",
                        "enum": ["all", "any", "groups"],
                        "default": "groups",
                        "description": "groups: pipe=OR comma=AND. Recommended for multi-GPU searches.",
                    },
                    "must_exclude": {
                        "type": "string",
                        "description": (
                            "Comma-separated terms to exclude. "
                            "Suggested: 'broken,cracked,no post,for parts,parts only,untested,"
                            "lcd,screen,chassis,housing,bios locked'"
                        ),
                    },
                    "max_price": {
                        "type": "number",
                        "default": 0,
                        "description": "Max price USD (0 = no limit)",
                    },
                    "min_price": {
                        "type": "number",
                        "default": 0,
                        "description": "Min price USD (0 = no limit)",
                    },
                    "pages": {
                        "type": "integer",
                        "default": 2,
                        "description": "Pages of eBay results to fetch (1 page ≈ 50 listings)",
                    },
                    "category_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "eBay category ID. "
                            "177946 = Laptop Motherboards & System Boards. "
                            "27386 = Graphics Cards (PCIe, for price comparison). "
                            "Leave empty to search all categories."
                        ),
                    },
                    "vram_weight": {
                        "type": "number",
                        "default": 0.6,
                        "description": (
                            "0–1. Weight of VRAM in GPU inference score. "
                            "Higher = VRAM is primary ranking factor. "
                            "Use 1.0 to rank purely by VRAM (ignores arch generation)."
                        ),
                    },
                    "arch_weight": {
                        "type": "number",
                        "default": 0.4,
                        "description": (
                            "0–1. Weight of architecture generation in GPU inference score. "
                            "Higher = prefer newer GPU arch (Ada > Ampere > Turing etc.). "
                            "Use 0.0 to ignore arch and rank purely by VRAM."
                        ),
                    },
                    "top_n": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max results to return after sorting",
                    },
                },
            },
        ),
        Tool(
            name="snipe_enrich",
            description=(
                "Deep-dive enrichment for a specific seller + listing. "
                "Runs BTF scraping and category history to fill partial trust scores (~20s). "
                "Use when snipe_search returns trust_partial=true on a promising listing."
            ),
            inputSchema={
                "type": "object",
                "required": ["seller_id", "listing_id"],
                "properties": {
                    "seller_id": {
                        "type": "string",
                        "description": "eBay seller platform ID (from snipe_search result seller_id field)",
                    },
                    "listing_id": {
                        "type": "string",
                        "description": "eBay listing platform ID (from snipe_search result id field)",
                    },
                    "query": {
                        "type": "string",
                        "default": "",
                        "description": "Original search query — provides market comp context for re-scoring",
                    },
                },
            },
        ),
        Tool(
            name="snipe_save",
            description="Persist a productive search for ongoing monitoring in the Snipe UI.",
            inputSchema={
                "type": "object",
                "required": ["name", "query"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable label, e.g. 'RTX 3070+ laptop boards under $250'",
                    },
                    "query": {
                        "type": "string",
                        "description": "The eBay search query string",
                    },
                    "filters_json": {
                        "type": "string",
                        "default": "{}",
                        "description": "JSON string of filter params to preserve (max_price, must_include, etc.)",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "snipe_search":
        return await _search(arguments)
    if name == "snipe_enrich":
        return await _enrich(arguments)
    if name == "snipe_save":
        return await _save(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _search(args: dict) -> list[TextContent]:
    from app.mcp.formatters import format_results

    # Build params — omit empty strings and zero numerics (except q)
    raw = {
        "q": args.get("query", ""),
        "must_include": args.get("must_include", ""),
        "must_include_mode": args.get("must_include_mode", "groups"),
        "must_exclude": args.get("must_exclude", ""),
        "max_price": args.get("max_price", 0),
        "min_price": args.get("min_price", 0),
        "pages": args.get("pages", 2),
        "category_id": args.get("category_id", ""),
    }
    params = {k: v for k, v in raw.items() if v != "" and v != 0 or k == "q"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_SNIPE_API}/api/search", params=params)
        resp.raise_for_status()

    formatted = format_results(
        resp.json(),
        vram_weight=float(args.get("vram_weight", 0.6)),
        arch_weight=float(args.get("arch_weight", 0.4)),
        top_n=int(args.get("top_n", 20)),
    )
    return [TextContent(type="text", text=json.dumps(formatted, indent=2))]


async def _enrich(args: dict) -> list[TextContent]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_SNIPE_API}/api/enrich",
            params={
                "seller": args["seller_id"],
                "listing_id": args["listing_id"],
                "query": args.get("query", ""),
            },
        )
        resp.raise_for_status()
    return [TextContent(type="text", text=json.dumps(resp.json(), indent=2))]


async def _save(args: dict) -> list[TextContent]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_SNIPE_API}/api/saved-searches",
            json={
                "name": args["name"],
                "query": args["query"],
                "filters_json": args.get("filters_json", "{}"),
            },
        )
        resp.raise_for_status()
    data = resp.json()
    return [TextContent(type="text", text=f"Saved (id={data.get('id')}): {args['name']}")]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_main())
