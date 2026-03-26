"""Snipe FastAPI — search endpoint wired to ScrapedEbayAdapter + TrustScorer."""
from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from circuitforge_core.config import load_env
from app.db.store import Store
from app.platforms import SearchFilters
from app.platforms.ebay.scraper import ScrapedEbayAdapter
from app.trust import TrustScorer

load_env(Path(".env"))
log = logging.getLogger(__name__)

_DB_PATH = Path(os.environ.get("SNIPE_DB", "data/snipe.db"))
_DB_PATH.parent.mkdir(exist_ok=True)

app = FastAPI(title="Snipe API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _parse_terms(raw: str) -> list[str]:
    """Split a comma-separated keyword string into non-empty, stripped terms."""
    return [t.strip() for t in raw.split(",") if t.strip()]


@app.get("/api/search")
def search(
    q: str = "",
    max_price: float = 0,
    min_price: float = 0,
    pages: int = 1,
    must_include: str = "",   # comma-separated; applied client-side only
    must_exclude: str = "",   # comma-separated; forwarded to eBay AND applied client-side
):
    if not q.strip():
        return {"listings": [], "trust_scores": {}, "sellers": {}, "market_price": None}

    filters = SearchFilters(
        max_price=max_price if max_price > 0 else None,
        min_price=min_price if min_price > 0 else None,
        pages=max(1, pages),
        must_include=_parse_terms(must_include),
        must_exclude=_parse_terms(must_exclude),
    )

    # Each adapter gets its own Store (SQLite connection) — required for thread safety.
    # search() and get_completed_sales() run concurrently; they write to different tables
    # so SQLite file-level locking is the only contention point.
    search_adapter = ScrapedEbayAdapter(Store(_DB_PATH))
    comps_adapter = ScrapedEbayAdapter(Store(_DB_PATH))

    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            listings_future = ex.submit(search_adapter.search, q, filters)
            comps_future = ex.submit(comps_adapter.get_completed_sales, q, pages)
            listings = listings_future.result()
            comps_future.result()  # wait; side-effect is saving market comp to DB
    except Exception as e:
        log.warning("eBay scrape failed: %s", e)
        raise HTTPException(status_code=502, detail=f"eBay search failed: {e}")

    # Use search_adapter's store for post-processing — it has the sellers already written
    store = search_adapter._store
    store.save_listings(listings)

    scorer = TrustScorer(store)
    trust_scores_list = scorer.score_batch(listings, q)

    # Market comp written by comps_adapter — read from a fresh connection to avoid
    # cross-thread connection reuse
    comp_store = Store(_DB_PATH)
    query_hash = hashlib.md5(q.encode()).hexdigest()
    comp = comp_store.get_market_comp("ebay", query_hash)
    market_price = comp.median_price if comp else None

    # Serialize — keyed by platform_listing_id for easy Vue lookup
    trust_map = {
        listing.platform_listing_id: dataclasses.asdict(ts)
        for listing, ts in zip(listings, trust_scores_list)
        if ts is not None
    }
    seller_map = {
        listing.seller_platform_id: dataclasses.asdict(
            store.get_seller("ebay", listing.seller_platform_id)
        )
        for listing in listings
        if listing.seller_platform_id
        and store.get_seller("ebay", listing.seller_platform_id)
    }

    return {
        "listings": [dataclasses.asdict(l) for l in listings],
        "trust_scores": trust_map,
        "sellers": seller_map,
        "market_price": market_price,
    }
