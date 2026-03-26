"""Snipe FastAPI — search endpoint wired to ScrapedEbayAdapter + TrustScorer."""
from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
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


@app.get("/api/search")
def search(q: str = "", max_price: float = 0, min_price: float = 0):
    if not q.strip():
        return {"listings": [], "trust_scores": {}, "sellers": {}, "market_price": None}

    store = Store(_DB_PATH)
    adapter = ScrapedEbayAdapter(store)

    filters = SearchFilters(
        max_price=max_price if max_price > 0 else None,
        min_price=min_price if min_price > 0 else None,
    )

    try:
        listings = adapter.search(q, filters)
        adapter.get_completed_sales(q)  # warm market comp cache
    except Exception as e:
        log.warning("eBay scrape failed: %s", e)
        raise HTTPException(status_code=502, detail=f"eBay search failed: {e}")

    store.save_listings(listings)

    scorer = TrustScorer(store)
    trust_scores_list = scorer.score_batch(listings, q)

    # Market comp
    query_hash = hashlib.md5(q.encode()).hexdigest()
    comp = store.get_market_comp("ebay", query_hash)
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
