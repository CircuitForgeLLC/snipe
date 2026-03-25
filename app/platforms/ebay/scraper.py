"""Scraper-based eBay adapter — free tier, no API key required.

Data available from search results HTML (single page load):
  ✅ title, price, condition, photos, URL
  ✅ seller username, feedback count, feedback ratio
  ❌ account registration date  →  account_age_score = None  (score_is_partial)
  ❌ category history           →  category_history_score = None (score_is_partial)

This is the MIT discovery layer. EbayAdapter (paid/CF proxy) unlocks full trust scores.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.db.models import Listing, MarketComp, Seller
from app.db.store import Store
from app.platforms import PlatformAdapter, SearchFilters

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_SELLER_RE = re.compile(r"^(.+?)\s+\(([0-9,]+)\)\s+([\d.]+)%")
_PRICE_RE = re.compile(r"[\d,]+\.?\d*")
_ITEM_ID_RE = re.compile(r"/itm/(\d+)")


# ---------------------------------------------------------------------------
# Pure HTML parsing functions (unit-testable, no HTTP)
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> float:
    """Extract first numeric value from price text.

    Handles '$950.00', '$900.00 to $1,050.00', '$1,234.56/ea'.
    Takes the lower bound for price ranges (conservative for trust scoring).
    """
    m = _PRICE_RE.search(text.replace(",", ""))
    return float(m.group()) if m else 0.0


def _parse_seller(text: str) -> tuple[str, int, float]:
    """Parse eBay seller-info text into (username, feedback_count, feedback_ratio).

    Input format: 'tech_seller (1,234) 99.1% positive feedback'
    Returns ('tech_seller', 1234, 0.991).
    Falls back gracefully if the format doesn't match.
    """
    text = text.strip()
    m = _SELLER_RE.match(text)
    if not m:
        return (text.split()[0] if text else ""), 0, 0.0
    return m.group(1).strip(), int(m.group(2).replace(",", "")), float(m.group(3)) / 100.0


def scrape_listings(html: str) -> list[Listing]:
    """Parse eBay search results HTML into Listing objects."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for item in soup.select("li.s-item"):
        # eBay injects a ghost "Shop on eBay" promo as the first item — skip it
        title_el = item.select_one("h3.s-item__title span, div.s-item__title span")
        if not title_el or "Shop on eBay" in title_el.text:
            continue

        link_el = item.select_one("a.s-item__link")
        url = link_el["href"].split("?")[0] if link_el else ""
        id_match = _ITEM_ID_RE.search(url)
        platform_listing_id = (
            id_match.group(1) if id_match else hashlib.md5(url.encode()).hexdigest()[:12]
        )

        price_el = item.select_one("span.s-item__price")
        price = _parse_price(price_el.text) if price_el else 0.0

        condition_el = item.select_one("span.SECONDARY_INFO")
        condition = condition_el.text.strip().lower() if condition_el else ""

        seller_el = item.select_one("span.s-item__seller-info-text")
        seller_username = _parse_seller(seller_el.text)[0] if seller_el else ""

        # Images are lazy-loaded — check data-src before src
        img_el = item.select_one("div.s-item__image-wrapper img, .s-item__image img")
        photo_url = ""
        if img_el:
            photo_url = img_el.get("data-src") or img_el.get("src") or ""

        results.append(Listing(
            platform="ebay",
            platform_listing_id=platform_listing_id,
            title=title_el.text.strip(),
            price=price,
            currency="USD",
            condition=condition,
            seller_platform_id=seller_username,
            url=url,
            photo_urls=[photo_url] if photo_url else [],
            listing_age_days=0,  # not reliably in search HTML
        ))

    return results


def scrape_sellers(html: str) -> dict[str, Seller]:
    """Extract Seller objects from search results HTML.

    Returns a dict keyed by username. account_age_days and category_history_json
    are left empty — they require a separate seller profile page fetch, which
    would mean one extra HTTP request per seller. That data gap is what separates
    free (scraper) from paid (API) tier.
    """
    soup = BeautifulSoup(html, "lxml")
    sellers: dict[str, Seller] = {}

    for item in soup.select("li.s-item"):
        seller_el = item.select_one("span.s-item__seller-info-text")
        if not seller_el:
            continue
        username, count, ratio = _parse_seller(seller_el.text)
        if username and username not in sellers:
            sellers[username] = Seller(
                platform="ebay",
                platform_seller_id=username,
                username=username,
                account_age_days=0,       # not available from search HTML
                feedback_count=count,
                feedback_ratio=ratio,
                category_history_json="{}", # not available from search HTML
            )

    return sellers


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class ScrapedEbayAdapter(PlatformAdapter):
    """
    Scraper-based eBay adapter implementing PlatformAdapter with no API key.

    Extracts seller feedback directly from search result cards — no extra
    per-seller page requests. The two unavailable signals (account_age,
    category_history) cause TrustScorer to set score_is_partial=True.
    """

    def __init__(self, store: Store, delay: float = 0.5):
        self._store = store
        self._delay = delay
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def _get(self, params: dict) -> str:
        time.sleep(self._delay)
        resp = self._session.get(EBAY_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.text

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        params: dict = {"_nkw": query, "_sop": "15", "_ipg": "48"}

        if filters.max_price:
            params["_udhi"] = str(filters.max_price)
        if filters.min_price:
            params["_udlo"] = str(filters.min_price)
        if filters.condition:
            cond_map = {
                "new": "1000", "used": "3000",
                "open box": "2500", "for parts": "7000",
            }
            codes = [cond_map[c] for c in filters.condition if c in cond_map]
            if codes:
                params["LH_ItemCondition"] = "|".join(codes)

        html = self._get(params)
        listings = scrape_listings(html)

        # Cache seller objects extracted from the same page
        for seller in scrape_sellers(html).values():
            self._store.save_seller(seller)

        return listings

    def get_seller(self, seller_platform_id: str) -> Optional[Seller]:
        # Sellers are pre-populated during search(); no extra fetch needed
        return self._store.get_seller("ebay", seller_platform_id)

    def get_completed_sales(self, query: str) -> list[Listing]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if self._store.get_market_comp("ebay", query_hash):
            return []  # cache hit — comp already stored

        params = {
            "_nkw": query,
            "LH_Sold": "1",
            "LH_Complete": "1",
            "_sop": "13",  # price + shipping: lowest first
            "_ipg": "48",
        }
        try:
            html = self._get(params)
            listings = scrape_listings(html)
            prices = sorted(l.price for l in listings if l.price > 0)
            if prices:
                median = prices[len(prices) // 2]
                self._store.save_market_comp(MarketComp(
                    platform="ebay",
                    query_hash=query_hash,
                    median_price=median,
                    sample_count=len(prices),
                    expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                ))
            return listings
        except Exception:
            return []
