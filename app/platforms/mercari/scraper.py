"""Mercari search + listing page scraper.

Uses the shared eBay browser pool (headed Chromium + Xvfb + playwright-stealth)
which already bypasses Cloudflare Turnstile.  Import the pool singleton from
ebay.browser_pool so both platforms share the same warm Chromium instances.

Seller data is NOT available from search results HTML — only from individual
listing pages.  The adapter lazily fetches listing pages in get_seller().
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup, NavigableString

log = logging.getLogger(__name__)

_BASE = "https://www.mercari.com"
_SEARCH_PATH = "/search/"
_ITEM_PATH = "/us/item/"

_PRICE_RE = re.compile(r"[\d,]+\.?\d*")
_POSTED_RE = re.compile(r"(\d{2})/(\d{2})/(\d{2,4})")  # MM/DD/YY or MM/DD/YYYY


def build_search_url(query: str, max_price: Optional[float] = None, min_price: Optional[float] = None) -> str:
    # No explicit sortBy — Mercari's default (relevance) is the most useful order.
    # "sortBy=SORT_SCORE" was a deprecated value that returns an empty results page.
    params: dict = {"keyword": query}
    # Mercari accepts priceMin/priceMax as whole dollar strings (not cents)
    if min_price is not None and min_price > 0:
        params["priceMin"] = str(int(min_price))
    if max_price is not None and max_price > 0:
        params["priceMax"] = str(int(max_price))
    return f"{_BASE}{_SEARCH_PATH}?{urlencode(params)}"


def parse_search_html(html: str) -> list[dict]:
    """Parse Mercari search results HTML into a list of raw listing dicts."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    for item in soup.find_all(attrs={"data-testid": "ItemContainer"}):
        pid = item.get("data-productid", "")
        if not pid:
            continue

        parent = item.parent
        href = parent.get("href") if parent and parent.name == "a" else None
        url = f"{_BASE}{href}" if href else f"{_BASE}{_ITEM_PATH}{pid}/"

        name_el = item.find(attrs={"data-testid": "ItemName"})
        title = name_el.get_text(strip=True) if name_el else ""

        price = _extract_current_price(item)
        img_el = item.find("img")
        photo_url = img_el.get("src", "") if img_el else ""

        results.append({
            "product_id": pid,
            "url": url,
            "title": title,
            "price": price,
            "photo_url": photo_url,
            "brand": item.get("data-brand", ""),
            "is_on_sale": item.get("data-is-on-sale") == "true",
        })

    return results


def _extract_current_price(item: BeautifulSoup) -> float:
    """Return the current (non-strikethrough) price from an ItemContainer."""
    price_el = item.find(attrs={"data-testid": "ProductThumbItemPrice"})
    if not price_el:
        return 0.0

    # Direct text nodes are the current price; the nested span is the original.
    price_text = "".join(
        str(c) for c in price_el.children if isinstance(c, NavigableString)
    ).strip()

    m = _PRICE_RE.search(price_text)
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            pass
    return 0.0


def parse_listing_html(html: str, product_id: str) -> dict:
    """Parse a Mercari listing page into a raw seller dict."""
    soup = BeautifulSoup(html, "html.parser")

    def _text(testid: str) -> str:
        el = soup.find(attrs={"data-testid": testid})
        return el.get_text(strip=True) if el else ""

    username_raw = _text("ItemDetailsSellerUserName")
    username = username_raw.lstrip("@")

    num_sales = _safe_int(_text("NumSales"))
    rating_count = _safe_int(_text("SellerRatingCount"))

    stars = 0.0
    rw = soup.find(attrs={"data-testid": "ReviewStarsWrapper"})
    if rw:
        try:
            stars = float(rw.get("data-stars", 0))
        except (ValueError, TypeError):
            pass

    condition = _text("ItemDetailsCondition").lower()
    posted_text = _text("ItemDetailsPosted")
    listing_age_days = _parse_listing_age(posted_text)

    price_text = _text("ItemPrice")
    price = 0.0
    m = _PRICE_RE.search(price_text.replace(",", ""))
    if m:
        try:
            price = float(m.group())
        except ValueError:
            pass

    return {
        "product_id": product_id,
        "username": username,
        "num_sales": num_sales,       # completed sales → maps to feedback_count
        "rating_count": rating_count,  # number of reviews (additional signal)
        "stars": stars,                # 0.0–5.0 → divide by 5 = feedback_ratio
        "condition": condition,
        "listing_age_days": listing_age_days,
        "price": price,
    }


def _safe_int(text: str) -> int:
    m = _PRICE_RE.search(text.replace(",", ""))
    if m:
        try:
            return int(float(m.group()))
        except ValueError:
            pass
    return 0


def _parse_listing_age(posted_text: str) -> int:
    """Convert a posted date like '04/10/26' to days since posted."""
    from datetime import datetime, timezone
    m = _POSTED_RE.search(posted_text)
    if not m:
        return 0
    try:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        posted = datetime(year, month, day, tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - posted).days
    except (ValueError, OverflowError):
        return 0
