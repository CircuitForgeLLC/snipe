"""eBay Browse + Trading API adapter."""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

_SHOPPING_BASE = "https://open.api.ebay.com/shopping"

# Rate limiting for Shopping API GetUserProfile calls.
# Enrichment is incremental — these caps spread API calls across multiple
# searches rather than bursting on first encounter with a new seller batch.
_SHOPPING_API_MAX_PER_SEARCH = 5          # sellers enriched per search call
_SHOPPING_API_INTER_REQUEST_DELAY = 0.5   # seconds between successive calls
_SELLER_ENRICH_TTL_HOURS = 24             # skip re-enrichment within this window

from app.db.models import Listing, MarketComp, Seller
from app.db.protocol import SharedTableProtocol
from app.platforms import PlatformAdapter, SearchFilters
from app.platforms.ebay.auth import EbayTokenManager
from app.platforms.ebay.normaliser import normalise_listing, normalise_seller

_BROWSE_LIMIT = 200   # max items per Browse API page
_INSIGHTS_BASE = {
    "production": "https://api.ebay.com/buy/marketplace_insights/v1_beta",
    "sandbox":    "https://api.sandbox.ebay.com/buy/marketplace_insights/v1_beta",
}


def _build_browse_query(base_query: str, or_groups: list[list[str]], must_exclude: list[str]) -> str:
    """Convert OR groups + exclusions into Browse API boolean query syntax.

    Browse API uses SQL-like boolean: AND (implicit), OR (keyword), NOT (keyword).
    Parentheses work as grouping operators.
    Example: 'GPU (16gb OR 24gb OR 48gb) (nvidia OR rtx OR geforce) NOT "parts only"'
    """
    parts = [base_query.strip()]
    for group in or_groups:
        clean = [t.strip() for t in group if t.strip()]
        if len(clean) == 1:
            parts.append(clean[0])
        elif len(clean) > 1:
            parts.append(f"({' OR '.join(clean)})")
    for term in must_exclude:
        term = term.strip()
        if term:
            # Use minus syntax (-term / -"phrase") — Browse API's NOT keyword
            # over-filters dramatically in practice; minus works like web search negatives.
            parts.append(f'-"{term}"' if " " in term else f"-{term}")
    return " ".join(p for p in parts if p)

BROWSE_BASE = {
    "production": "https://api.ebay.com/buy/browse/v1",
    "sandbox":    "https://api.sandbox.ebay.com/buy/browse/v1",
}
# Note: seller lookup uses the Browse API with a seller filter, not a separate Seller API.
# The Commerce Identity /user endpoint returns the calling app's own identity (requires
# user OAuth, not app credentials). Seller metadata is extracted from Browse API inline
# seller fields. registrationDate is available in item detail responses via this path.


class EbayAdapter(PlatformAdapter):
    def __init__(self, token_manager: EbayTokenManager, shared_store: SharedTableProtocol, env: str = "production"):
        self._tokens = token_manager
        self._store = shared_store
        self._env = env
        self._browse_base = BROWSE_BASE[env]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._tokens.get_token()}"}

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        # Build Browse API boolean query from OR groups + exclusions
        browse_q = _build_browse_query(query, getattr(filters, "or_groups", []), filters.must_exclude)

        filter_parts: list[str] = []
        if filters.max_price:
            filter_parts.append(f"price:[..{filters.max_price}],priceCurrency:USD")
        if filters.min_price:
            filter_parts.append(f"price:[{filters.min_price}..],priceCurrency:USD")
        if filters.condition:
            cond_map = {
                "new": "NEW", "used": "USED",
                "open box": "OPEN_BOX", "for parts": "FOR_PARTS_NOT_WORKING",
            }
            ebay_conds = [cond_map[c] for c in filters.condition if c in cond_map]
            if ebay_conds:
                filter_parts.append(f"conditions:{{{','.join(ebay_conds)}}}")

        base_params: dict = {"q": browse_q, "limit": _BROWSE_LIMIT}
        if filter_parts:
            base_params["filter"] = ",".join(filter_parts)
        if filters.category_id:
            base_params["category_ids"] = filters.category_id

        pages = max(1, filters.pages)
        seen_ids: set[str] = set()
        listings: list[Listing] = []
        sellers_to_save: dict[str, Seller] = {}

        for page in range(pages):
            params = {**base_params, "offset": page * _BROWSE_LIMIT}
            resp = requests.get(
                f"{self._browse_base}/item_summary/search",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("itemSummaries", [])
            if not items:
                break  # no more results

            for item in items:
                listing = normalise_listing(item)
                if listing.platform_listing_id not in seen_ids:
                    seen_ids.add(listing.platform_listing_id)
                    listings.append(listing)
                    # Extract inline seller data available in item_summary
                    seller_raw = item.get("seller", {})
                    if seller_raw.get("username") and seller_raw["username"] not in sellers_to_save:
                        sellers_to_save[seller_raw["username"]] = normalise_seller(seller_raw)

            if not data.get("next"):
                break  # Browse API paginates via "next" href; absence = last page

        if sellers_to_save:
            self._store.save_sellers(list(sellers_to_save.values()))

        # Enrich sellers missing account_age_days via Shopping API (fast HTTP, no Playwright).
        # Capped at _SHOPPING_API_MAX_PER_SEARCH to avoid bursting the daily quota when
        # many new sellers appear in a single search batch.
        needs_age = [s.platform_seller_id for s in sellers_to_save.values()
                     if s.account_age_days is None]
        if needs_age:
            self.enrich_sellers_shopping_api(needs_age[:_SHOPPING_API_MAX_PER_SEARCH])

        return listings

    def enrich_sellers_shopping_api(self, usernames: list[str]) -> None:
        """Fetch RegistrationDate for sellers via Shopping API GetUserProfile.

        Uses app-level Bearer token — no user OAuth required. Silently skips
        on rate limit (error 1.21) or any other failure so the search response
        is never blocked. BTF scraping remains the fallback for the scraper adapter.

        Rate limiting: _SHOPPING_API_INTER_REQUEST_DELAY between calls; sellers
        enriched within _SELLER_ENRICH_TTL_HOURS are skipped (account age doesn't
        change day to day). Callers should already cap the list length.
        """
        token = self._tokens.get_token()
        headers = {
            "X-EBAY-API-IAF-TOKEN": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0",
        }
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_SELLER_ENRICH_TTL_HOURS)
        first = True
        for username in usernames:
            try:
                # Skip recently enriched sellers — account age doesn't change daily.
                seller = self._store.get_seller("ebay", username)
                if seller and seller.fetched_at:
                    try:
                        ft = datetime.fromisoformat(seller.fetched_at.replace("Z", "+00:00"))
                        if ft.tzinfo is None:
                            ft = ft.replace(tzinfo=timezone.utc)
                        if ft > cutoff and seller.account_age_days is not None:
                            continue
                    except ValueError:
                        pass

                if not first:
                    import time as _time
                    _time.sleep(_SHOPPING_API_INTER_REQUEST_DELAY)
                first = False

                resp = requests.get(
                    _SHOPPING_BASE,
                    headers=headers,
                    params={
                        "callname": "GetUserProfile",
                        "appid": self._tokens.client_id,
                        "siteid": "0",
                        "version": "967",
                        "UserID": username,
                        "responseencoding": "JSON",
                    },
                    timeout=10,
                )
                data = resp.json()
                if data.get("Ack") != "Success":
                    errors = data.get("Errors", [])
                    if any(e.get("ErrorCode") == "1.21" for e in errors):
                        log.debug("Shopping API rate-limited for %s — BTF fallback", username)
                    continue
                reg_date = data.get("User", {}).get("RegistrationDate")
                if reg_date:
                    dt = datetime.fromisoformat(reg_date.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - dt).days
                    seller = self._store.get_seller("ebay", username)
                    if seller:
                        self._store.save_seller(replace(seller, account_age_days=age_days))
                        log.debug("Shopping API: %s registered %d days ago", username, age_days)
            except Exception as e:
                log.debug("Shopping API enrich failed for %s: %s", username, e)

    # ── Trading API GetUser (requires user OAuth token) ───────────────────────

    _TRADING_API_URL = "https://api.ebay.com/ws/api.dll"
    _TRADING_API_COMPATIBILITY = "1283"

    def enrich_seller_trading_api(self, username: str, user_access_token: str) -> bool:
        """Enrich a seller's account_age_days using Trading API GetUser.

        Uses the connected user's OAuth access token (Authorization Code flow),
        which bypasses Shopping API rate limits and works even when the Shopping
        API GetUserProfile call is throttled.

        Unlike BTF scraping, this is a clean API call (~200ms, no Playwright).
        Called from the search endpoint when the requesting user has connected
        their eBay account.

        Returns True if enrichment succeeded, False on any failure.
        """
        xml_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<GetUserRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
            f'<UserID>{username}</UserID>'
            '</GetUserRequest>'
        )
        try:
            resp = requests.post(
                self._TRADING_API_URL,
                headers={
                    "X-EBAY-API-CALL-NAME": "GetUser",
                    "X-EBAY-API-SITEID": "0",
                    "X-EBAY-API-COMPATIBILITY-LEVEL": self._TRADING_API_COMPATIBILITY,
                    "X-EBAY-API-IAF-TOKEN": f"Bearer {user_access_token}",
                    "Content-Type": "text/xml",
                },
                data=xml_body.encode("utf-8"),
                timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            ns = {"e": "urn:ebay:apis:eBLBaseComponents"}

            ack = root.findtext("e:Ack", namespaces=ns)
            if ack not in ("Success", "Warning"):
                errors = [e.findtext("e:LongMessage", namespaces=ns, default="")
                          for e in root.findall("e:Errors", namespaces=ns)]
                log.debug("Trading API GetUser failed for %s: %s", username, errors)
                return False

            reg_date = root.findtext("e:User/e:RegistrationDate", namespaces=ns)
            if not reg_date:
                return False

            dt = datetime.fromisoformat(reg_date.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            seller = self._store.get_seller("ebay", username)
            if seller:
                self._store.save_seller(replace(seller, account_age_days=age_days))
                log.debug("Trading API GetUser: %s registered %d days ago", username, age_days)
            return True

        except Exception as exc:
            log.debug("Trading API GetUser failed for %s: %s", username, exc)
            return False

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

    def get_completed_sales(self, query: str, pages: int = 1) -> list[Listing]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if self._store.get_market_comp("ebay", query_hash):
            return []  # cache hit

        prices: list[float] = []
        try:
            # Marketplace Insights API returns sold/completed items — best source for comps.
            # Falls back gracefully to Browse API active listings if the endpoint is
            # unavailable (requires buy.marketplace.insights scope).
            insights_base = _INSIGHTS_BASE.get(self._env, _INSIGHTS_BASE["production"])
            resp = requests.get(
                f"{insights_base}/item_summary/search",
                headers=self._headers(),
                params={"q": query, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE}"},
            )
            if resp.status_code in (403, 404):
                # 403 = scope not granted; 404 = endpoint not available for this app tier.
                # Both mean: fall back to active listing prices via Browse API.
                log.info("comps api: Marketplace Insights unavailable (%d), falling back to Browse API", resp.status_code)
                raise PermissionError("Marketplace Insights not available")
            resp.raise_for_status()
            items = resp.json().get("itemSummaries", [])
            prices = [float(i["lastSoldPrice"]["value"]) for i in items if "lastSoldPrice" in i]
            log.info("comps api: Marketplace Insights returned %d items, %d with lastSoldPrice", len(items), len(prices))
        except PermissionError:
            # Fallback: use active listing prices (less accurate but always available)
            try:
                resp = requests.get(
                    f"{self._browse_base}/item_summary/search",
                    headers=self._headers(),
                    params={"q": query, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE}"},
                )
                resp.raise_for_status()
                items = resp.json().get("itemSummaries", [])
                prices = [float(i["price"]["value"]) for i in items if "price" in i]
                log.info("comps api: Browse API fallback returned %d items, %d with price", len(items), len(prices))
            except Exception:
                log.warning("comps api: Browse API fallback failed for %r", query, exc_info=True)
                return []
        except Exception:
            log.warning("comps api: unexpected error for %r", query, exc_info=True)
            return []

        if not prices:
            log.warning("comps api: 0 valid prices extracted — no comp saved for %r", query)
            return []

        prices.sort()
        n = len(prices)
        median = (prices[n // 2 - 1] + prices[n // 2]) / 2 if n % 2 == 0 else prices[n // 2]
        self._store.save_market_comp(MarketComp(
            platform="ebay",
            query_hash=query_hash,
            median_price=median,
            sample_count=n,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        ))
        return []
