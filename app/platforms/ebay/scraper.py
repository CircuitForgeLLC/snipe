"""Scraper-based eBay adapter — free tier, no API key required.

Data available from search results HTML (single page load):
  ✅ title, price, condition, photos, URL
  ✅ seller username, feedback count, feedback ratio
  ❌ account registration date  →  enriched async via BTF /itm/ scrape
  ❌ category history           →  enriched async via _ssn seller search page

This is the MIT discovery layer. EbayAdapter (paid/CF proxy) unlocks full trust scores.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

from bs4 import BeautifulSoup

from app.db.models import Listing, MarketComp, Seller
from app.db.store import Store
from app.platforms import PlatformAdapter, SearchFilters

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"
EBAY_ITEM_URL   = "https://www.ebay.com/itm/"
_HTML_CACHE_TTL = 300  # seconds — 5 minutes
_JOINED_RE = re.compile(r"Joined\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})", re.I)
# Matches "username (1,234) 99.1% positive feedback" on /itm/ listing pages.
# Capture groups: 1=raw_count ("1,234"), 2=ratio_pct ("99.1").
_ITEM_FEEDBACK_RE = re.compile(r'\((\d[\d,]*)\)\s*([\d.]+)%\s*positive', re.I)
_MONTH_MAP = {m: i+1 for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
)}

# Module-level cache persists across per-request adapter instantiations.
# Keyed by URL; value is (html, expiry_timestamp).
_html_cache: dict[str, tuple[str, float]] = {}

# Cycle through display numbers :200–:299 so concurrent/sequential Playwright
# calls don't collide on the Xvfb lock file from the previous run.
_display_counter = itertools.cycle(range(200, 300))

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
_FEEDBACK_RE = re.compile(r"([\d.]+)%\s+positive\s+\(([0-9,]+)\)", re.I)
_PRICE_RE = re.compile(r"[\d,]+\.?\d*")
_ITEM_ID_RE = re.compile(r"/itm/(\d+)")
_TIME_LEFT_RE = re.compile(r"(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s\s*)?left", re.I)
_PARENS_COUNT_RE = re.compile(r"\((\d{1,6})\)")

# Maps title-keyword fragments → internal MetadataScorer category keys.
# Checked in order — first match wins. Broader terms intentionally listed last.
_CATEGORY_KEYWORDS: list[tuple[frozenset[str], str]] = [
    (frozenset(["cell phone", "smartphone", "mobile phone"]), "CELL_PHONES"),
    (frozenset(["video game", "gaming", "console", "playstation", "xbox", "nintendo"]), "VIDEO_GAMES"),
    (frozenset(["computer", "tablet", "laptop", "notebook", "chromebook"]), "COMPUTERS_TABLETS"),
    (frozenset(["electronic"]), "ELECTRONICS"),
]


def _classify_category_label(text: str) -> Optional[str]:
    """Map an eBay category label to an internal MetadataScorer key, or None."""
    lower = text.lower()
    for keywords, key in _CATEGORY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return key
    return None


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


def _parse_time_left(text: str) -> Optional[timedelta]:
    """Parse eBay time-left text into a timedelta.

    Handles '3d 14h left', '14h 23m left', '23m 45s left'.
    Returns None if text doesn't match (i.e. fixed-price listing).
    """
    if not text:
        return None
    m = _TIME_LEFT_RE.search(text)
    if not m or not any(m.groups()):
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    if days == hours == minutes == seconds == 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def _extract_seller_from_card(card) -> tuple[str, int, float]:
    """Extract (username, feedback_count, feedback_ratio) from an s-card element.

    New eBay layout has seller username and feedback as separate su-styled-text spans.
    We find the feedback span by regex, then take the immediately preceding text as username.
    """
    texts = [s.get_text(strip=True) for s in card.select("span.su-styled-text") if s.get_text(strip=True)]
    username, count, ratio = "", 0, 0.0
    for i, t in enumerate(texts):
        m = _FEEDBACK_RE.search(t)
        if m:
            ratio = float(m.group(1)) / 100.0
            count = int(m.group(2).replace(",", ""))
            # Username is the span just before the feedback span
            if i > 0:
                username = texts[i - 1].strip()
            break
    return username, count, ratio


def scrape_listings(html: str) -> list[Listing]:
    """Parse eBay search results HTML into Listing objects."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for item in soup.select("li.s-card"):
        # Skip promos: no data-listingid or title is "Shop on eBay"
        platform_listing_id = item.get("data-listingid", "")
        if not platform_listing_id:
            continue

        title_el = item.select_one("div.s-card__title")
        if not title_el or "Shop on eBay" in title_el.get_text():
            continue

        link_el = item.select_one('a.s-card__link[href*="/itm/"]')
        url = link_el["href"].split("?")[0] if link_el else ""

        price_el = item.select_one("span.s-card__price")
        price = _parse_price(price_el.get_text()) if price_el else 0.0

        condition_el = item.select_one("div.s-card__subtitle")
        condition = condition_el.get_text(strip=True).split("·")[0].strip().lower() if condition_el else ""

        seller_username, _, _ = _extract_seller_from_card(item)

        img_el = item.select_one("img.s-card__image")
        photo_url = img_el.get("src") or img_el.get("data-src") or "" if img_el else ""

        # Auction detection via time-left text patterns in card spans
        time_remaining = None
        for span in item.select("span.su-styled-text"):
            t = span.get_text(strip=True)
            td = _parse_time_left(t)
            if td:
                time_remaining = td
                break
        buying_format = "auction" if time_remaining is not None else "fixed_price"
        ends_at = (datetime.now(timezone.utc) + time_remaining).isoformat() if time_remaining else None

        # Strip eBay's screen-reader accessibility text injected into title links.
        # get_text() is CSS-blind and picks up visually-hidden spans.
        raw_title = title_el.get_text(separator=" ", strip=True)
        title = re.sub(r"\s*Opens in a new window or tab\s*", "", raw_title, flags=re.IGNORECASE).strip()

        results.append(Listing(
            platform="ebay",
            platform_listing_id=platform_listing_id,
            title=title,
            price=price,
            currency="USD",
            condition=condition,
            seller_platform_id=seller_username,
            url=url,
            photo_urls=[photo_url] if photo_url else [],
            listing_age_days=0,
            buying_format=buying_format,
            ends_at=ends_at,
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

    for item in soup.select("li.s-card"):
        if not item.get("data-listingid"):
            continue
        username, count, ratio = _extract_seller_from_card(item)
        if username and username not in sellers:
            sellers[username] = Seller(
                platform="ebay",
                platform_seller_id=username,
                username=username,
                account_age_days=None,    # not fetched at scraper tier
                feedback_count=count,
                feedback_ratio=ratio,
                category_history_json="{}", # not available from search HTML
            )

    return sellers


def scrape_seller_categories(html: str) -> dict[str, int]:
    """Parse category distribution from a seller's _ssn search page.

    eBay renders category refinements in the left sidebar.  We scan all
    anchor-text blocks for recognisable category labels and accumulate
    listing counts from the adjacent parenthetical "(N)" strings.

    Returns a dict like {"ELECTRONICS": 45, "CELL_PHONES": 23}.
    Empty dict = no recognisable categories found (score stays None).
    """
    soup = BeautifulSoup(html, "lxml")
    counts: dict[str, int] = {}

    # eBay sidebar refinement links contain the category label and a count.
    # Multiple layout variants exist — scan broadly and classify by keyword.
    for el in soup.select("a[href*='_sacat='], li.x-refine__main__list--value a"):
        text = el.get_text(separator=" ", strip=True)
        key = _classify_category_label(text)
        if not key:
            continue
        m = _PARENS_COUNT_RE.search(text)
        count = int(m.group(1)) if m else 1
        counts[key] = counts.get(key, 0) + count

    return counts


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

    def __init__(self, shared_store: Store, delay: float = 1.0):
        self._store = shared_store
        self._delay = delay

    def _fetch_url(self, url: str) -> str:
        """Core Playwright fetch — stealthed headed Chromium via Xvfb.

        Shared by both search (_get) and BTF item-page enrichment (_fetch_item_html).
        Results cached for _HTML_CACHE_TTL seconds.
        """
        cached = _html_cache.get(url)
        if cached and time.time() < cached[1]:
            return cached[0]

        time.sleep(self._delay)

        import os
        import subprocess
        display_num = next(_display_counter)
        display = f":{display_num}"
        xvfb = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x800x24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        env = os.environ.copy()
        env["DISPLAY"] = display

        try:
            from playwright.sync_api import (
                sync_playwright,  # noqa: PLC0415 — lazy: only needed in Docker
            )
            from playwright_stealth import Stealth  # noqa: PLC0415

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=False,
                    env=env,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                ctx = browser.new_context(
                    user_agent=_HEADERS["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                )
                page = ctx.new_page()
                Stealth().apply_stealth_sync(page)
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2000)  # let any JS challenges resolve
                html = page.content()
                browser.close()
        finally:
            xvfb.terminate()
            xvfb.wait()

        _html_cache[url] = (html, time.time() + _HTML_CACHE_TTL)
        return html

    def _get(self, params: dict) -> str:
        """Fetch eBay search results HTML. params → query string appended to EBAY_SEARCH_URL."""
        url = EBAY_SEARCH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return self._fetch_url(url)

    def _fetch_item_html(self, item_id: str) -> str:
        """Fetch a single eBay listing page. /itm/ pages pass Kasada; /usr/ pages do not.

        Browse API returns itemId as "v1|123456789012|0"; extract the numeric
        segment so the URL resolves correctly (scraper IDs are already numeric).
        """
        if "|" in item_id:
            item_id = item_id.split("|")[1]
        return self._fetch_url(f"{EBAY_ITEM_URL}{item_id}")

    @staticmethod
    def _parse_joined_date(html: str) -> Optional[int]:
        """Parse 'Joined {Mon} {Year}' from a listing page BTF seller card.

        Returns account_age_days (int) or None if the date is not found.
        eBay renders this as a span.ux-textspans inside the seller section.
        """
        m = _JOINED_RE.search(html)
        if not m:
            return None
        month_str, year_str = m.group(1)[:3].capitalize(), m.group(2)
        month = _MONTH_MAP.get(month_str)
        if not month:
            return None
        try:
            reg_date = datetime(int(year_str), month, 1, tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - reg_date).days
        except ValueError:
            return None

    @staticmethod
    def _parse_feedback_from_item(html: str) -> tuple[Optional[int], Optional[float]]:
        """Parse feedback count and ratio from a listing page seller card.

        Matches 'username (1,234) 99.1% positive feedback'.
        Returns (count, ratio) or (None, None) if not found.
        """
        m = _ITEM_FEEDBACK_RE.search(html)
        if not m:
            return None, None
        try:
            count = int(m.group(1).replace(",", ""))
            ratio = float(m.group(2)) / 100.0
            return count, ratio
        except ValueError:
            return None, None

    def enrich_sellers_btf(
        self,
        seller_to_listing: dict[str, str],
        max_workers: int = 2,
    ) -> None:
        """Background BTF enrichment — scrape /itm/ pages to fill in account_age_days.

        seller_to_listing: {seller_platform_id -> platform_listing_id}
          Only pass sellers whose account_age_days is None (unknown from API batch).
          Caller limits the dict to new/stale sellers to avoid redundant scrapes.

        Runs Playwright fetches in a thread pool (max_workers=2 by default to
        avoid hammering Kasada).  Updates seller records in the DB in-place.
        Does not raise — failures per-seller are silently skipped so the main
        search response is never blocked.
        """
        db_path = self._store._db_path  # capture for thread-local Store creation

        def _enrich_one(item: tuple[str, str]) -> None:
            seller_id, listing_id = item
            try:
                html = self._fetch_item_html(listing_id)
                age_days = self._parse_joined_date(html)
                fb_count, fb_ratio = self._parse_feedback_from_item(html)
                log.debug(
                    "BTF enrich: seller=%s age_days=%s feedback=%s ratio=%s",
                    seller_id, age_days, fb_count, fb_ratio,
                )
                if age_days is None and fb_count is None:
                    return   # nothing new to write
                thread_store = Store(db_path)
                seller = thread_store.get_seller("ebay", seller_id)
                if not seller:
                    log.warning("BTF enrich: seller %s not found in DB", seller_id)
                    return
                from dataclasses import replace
                updates: dict = {}
                if age_days is not None:
                    updates["account_age_days"] = age_days
                # Only overwrite feedback if the listing page found a real value —
                # prefer a fresh count over a 0 that came from a failed search parse.
                if fb_count is not None:
                    updates["feedback_count"] = fb_count
                if fb_ratio is not None:
                    updates["feedback_ratio"] = fb_ratio
                thread_store.save_seller(replace(seller, **updates))
            except Exception as exc:
                log.warning("BTF enrich failed for %s/%s: %s", seller_id, listing_id, exc)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(_enrich_one, seller_to_listing.items()))

    def enrich_sellers_categories(
        self,
        seller_platform_ids: list[str],
        max_workers: int = 2,
    ) -> None:
        """Scrape _ssn seller pages to populate category_history_json.

        Uses the same headed Playwright stack as search() — the _ssn=USERNAME
        filter is just a query param on the standard search template, so it
        passes Kasada identically.  Silently skips on failure so the main
        search response is never affected.
        """
        def _enrich_one(seller_id: str) -> None:
            try:
                html = self._get({"_ssn": seller_id, "_sop": "12", "_ipg": "48"})
                categories = scrape_seller_categories(html)
                if categories:
                    seller = self._store.get_seller("ebay", seller_id)
                    if seller:
                        from dataclasses import replace
                        updated = replace(seller, category_history_json=json.dumps(categories))
                        self._store.save_seller(updated)
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(_enrich_one, seller_platform_ids))

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        base_params: dict = {"_nkw": query, "_sop": "15", "_ipg": "48"}
        if filters.category_id:
            base_params["_sacat"] = filters.category_id

        if filters.max_price:
            base_params["_udhi"] = str(filters.max_price)
        if filters.min_price:
            base_params["_udlo"] = str(filters.min_price)
        if filters.condition:
            cond_map = {
                "new": "1000", "used": "3000",
                "open box": "2500", "for parts": "7000",
            }
            codes = [cond_map[c] for c in filters.condition if c in cond_map]
            if codes:
                base_params["LH_ItemCondition"] = "|".join(codes)

        # Append negative keywords to the eBay query — eBay supports "-term" in _nkw natively.
        # Multi-word phrases must be quoted: -"parts only" not -parts only (which splits the words).
        if filters.must_exclude:
            parts = []
            for t in filters.must_exclude:
                t = t.strip()
                if not t:
                    continue
                parts.append(f'-"{t}"' if " " in t else f"-{t}")
            base_params["_nkw"] = f"{base_params['_nkw']} {' '.join(parts)}"

        pages = max(1, filters.pages)
        page_params = [{**base_params, "_pgn": str(p)} for p in range(1, pages + 1)]

        with ThreadPoolExecutor(max_workers=min(pages, 3)) as ex:
            htmls = list(ex.map(self._get, page_params))

        seen_ids: set[str] = set()
        listings: list[Listing] = []
        sellers: dict[str, "Seller"] = {}
        for html in htmls:
            for listing in scrape_listings(html):
                if listing.platform_listing_id not in seen_ids:
                    seen_ids.add(listing.platform_listing_id)
                    listings.append(listing)
            sellers.update(scrape_sellers(html))

        self._store.save_sellers(list(sellers.values()))
        return listings

    def get_seller(self, seller_platform_id: str) -> Optional[Seller]:
        # Sellers are pre-populated during search(); no extra fetch needed
        return self._store.get_seller("ebay", seller_platform_id)

    def get_completed_sales(self, query: str, pages: int = 1) -> list[Listing]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if self._store.get_market_comp("ebay", query_hash):
            return []  # cache hit — comp already stored

        base_params = {
            "_nkw": query,
            "LH_Sold": "1",
            "LH_Complete": "1",
            "_sop": "13",  # sort by price+shipping, lowest first
            "_ipg": "48",
        }
        pages = max(1, pages)
        page_params = [{**base_params, "_pgn": str(p)} for p in range(1, pages + 1)]

        log.info("comps scrape: fetching %d page(s) of sold listings for %r", pages, query)
        try:
            with ThreadPoolExecutor(max_workers=min(pages, 3)) as ex:
                htmls = list(ex.map(self._get, page_params))

            seen_ids: set[str] = set()
            all_listings: list[Listing] = []
            for html in htmls:
                for listing in scrape_listings(html):
                    if listing.platform_listing_id not in seen_ids:
                        seen_ids.add(listing.platform_listing_id)
                        all_listings.append(listing)

            prices = sorted(l.price for l in all_listings if l.price > 0)
            if prices:
                mid = len(prices) // 2
                median = (prices[mid - 1] + prices[mid]) / 2 if len(prices) % 2 == 0 else prices[mid]
                self._store.save_market_comp(MarketComp(
                    platform="ebay",
                    query_hash=query_hash,
                    median_price=median,
                    sample_count=len(prices),
                    expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                ))
                log.info("comps scrape: saved market comp median=$%.2f from %d prices", median, len(prices))
            else:
                log.warning("comps scrape: %d listings parsed but 0 valid prices — no comp saved", len(all_listings))
            return all_listings
        except Exception:
            log.warning("comps scrape: failed for %r", query, exc_info=True)
            return []
