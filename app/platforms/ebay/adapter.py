"""eBay Browse API adapter."""
from __future__ import annotations
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests

from app.db.models import Listing, Seller, MarketComp
from app.db.store import Store
from app.platforms import PlatformAdapter, SearchFilters
from app.platforms.ebay.auth import EbayTokenManager
from app.platforms.ebay.normaliser import normalise_listing, normalise_seller

BROWSE_BASE = {
    "production": "https://api.ebay.com/buy/browse/v1",
    "sandbox":    "https://api.sandbox.ebay.com/buy/browse/v1",
}
# Note: seller lookup uses the Browse API with a seller filter, not a separate Seller API.
# The Commerce Identity /user endpoint returns the calling app's own identity (requires
# user OAuth, not app credentials). Seller metadata is extracted from Browse API inline
# seller fields. registrationDate is available in item detail responses via this path.


class EbayAdapter(PlatformAdapter):
    def __init__(self, token_manager: EbayTokenManager, store: Store, env: str = "production"):
        self._tokens = token_manager
        self._store = store
        self._browse_base = BROWSE_BASE[env]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._tokens.get_token()}"}

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        params: dict = {"q": query, "limit": 50}
        filter_parts = []
        if filters.max_price:
            filter_parts.append(f"price:[..{filters.max_price}],priceCurrency:USD")
        if filters.condition:
            cond_map = {"new": "NEW", "used": "USED", "open box": "OPEN_BOX", "for parts": "FOR_PARTS_NOT_WORKING"}
            ebay_conds = [cond_map[c] for c in filters.condition if c in cond_map]
            if ebay_conds:
                filter_parts.append(f"conditions:{{{','.join(ebay_conds)}}}")
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        resp = requests.get(f"{self._browse_base}/item_summary/search",
                            headers=self._headers(), params=params)
        resp.raise_for_status()
        items = resp.json().get("itemSummaries", [])
        return [normalise_listing(item) for item in items]

    def get_seller(self, seller_platform_id: str) -> Optional[Seller]:
        cached = self._store.get_seller("ebay", seller_platform_id)
        if cached:
            return cached
        try:
            resp = requests.get(
                f"{self._browse_base}/item_summary/search",
                headers={**self._headers(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                params={"seller": seller_platform_id, "limit": 1},
            )
            resp.raise_for_status()
            items = resp.json().get("itemSummaries", [])
            if not items:
                return None
            seller = normalise_seller(items[0].get("seller", {}))
            self._store.save_seller(seller)
            return seller
        except Exception:
            return None  # Caller handles None gracefully (partial score)

    def get_completed_sales(self, query: str) -> list[Listing]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        cached = self._store.get_market_comp("ebay", query_hash)
        if cached:
            return []  # Comp data is used directly; return empty to signal cache hit

        params = {"q": query, "limit": 20, "filter": "buyingOptions:{FIXED_PRICE}"}
        try:
            resp = requests.get(f"{self._browse_base}/item_summary/search",
                                headers=self._headers(), params=params)
            resp.raise_for_status()
            items = resp.json().get("itemSummaries", [])
            listings = [normalise_listing(item) for item in items]
            if listings:
                prices = sorted(l.price for l in listings)
                median = prices[len(prices) // 2]
                comp = MarketComp(
                    platform="ebay",
                    query_hash=query_hash,
                    median_price=median,
                    sample_count=len(prices),
                    expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                )
                self._store.save_market_comp(comp)
            return listings
        except Exception:
            return []
