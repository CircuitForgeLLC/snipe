"""Tests for the scraper-based eBay adapter.

Uses a minimal HTML fixture mirroring eBay's current s-card markup.
No HTTP requests are made — all tests operate on the pure parsing functions.
"""
import pytest
from datetime import timedelta
from app.platforms.ebay.scraper import (
    scrape_listings,
    scrape_sellers,
    _parse_price,
    _parse_time_left,
    _extract_seller_from_card,
)
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Minimal eBay search results HTML fixture (li.s-card schema)
# ---------------------------------------------------------------------------

_EBAY_HTML = """
<html><body>
<ul class="srp-results">
  <!-- Promo item: no data-listingid — must be skipped -->
  <li class="s-card">
    <div class="s-card__title">Shop on eBay</div>
  </li>

  <!-- Real listing 1: established seller, used, fixed price -->
  <li class="s-card" data-listingid="123456789">
    <div class="s-card__title">RTX 4090 Founders Edition GPU</div>
    <a class="s-card__link" href="https://www.ebay.com/itm/123456789?somequery=1"></a>
    <span class="s-card__price">$950.00</span>
    <div class="s-card__subtitle">Used · Free shipping</div>
    <img class="s-card__image" src="https://i.ebayimg.com/thumbs/1.jpg"/>
    <span class="su-styled-text">techguy</span>
    <span class="su-styled-text">99.1% positive (1,234)</span>
  </li>

  <!-- Real listing 2: price range, new, data-src photo -->
  <li class="s-card" data-listingid="987654321">
    <div class="s-card__title">RTX 4090 Gaming OC 24GB</div>
    <a class="s-card__link" href="https://www.ebay.com/itm/987654321"></a>
    <span class="s-card__price">$1,100.00 to $1,200.00</span>
    <div class="s-card__subtitle">New · Free shipping</div>
    <img class="s-card__image" data-src="https://i.ebayimg.com/thumbs/2.jpg" src=""/>
    <span class="su-styled-text">gpu_warehouse</span>
    <span class="su-styled-text">98.7% positive (450)</span>
  </li>

  <!-- Real listing 3: new account, suspicious price -->
  <li class="s-card" data-listingid="555000111">
    <div class="s-card__title">RTX 4090 BNIB Sealed</div>
    <a class="s-card__link" href="https://www.ebay.com/itm/555000111"></a>
    <span class="s-card__price">$499.00</span>
    <div class="s-card__subtitle">New</div>
    <img class="s-card__image" src="https://i.ebayimg.com/thumbs/3.jpg"/>
    <span class="su-styled-text">new_user_2024</span>
    <span class="su-styled-text">100.0% positive (2)</span>
  </li>
</ul>
</body></html>
"""

_AUCTION_HTML = """
<html><body>
<ul class="srp-results">
  <li class="s-card" data-listingid="777000999">
    <div class="s-card__title">Vintage Leica M6 Camera Body</div>
    <a class="s-card__link" href="https://www.ebay.com/itm/777000999"></a>
    <span class="s-card__price">$450.00</span>
    <div class="s-card__subtitle">Used</div>
    <img class="s-card__image" src="https://i.ebayimg.com/thumbs/cam.jpg"/>
    <span class="su-styled-text">camera_dealer</span>
    <span class="su-styled-text">97.5% positive (800)</span>
    <span class="su-styled-text">2h 30m left</span>
  </li>
</ul>
</body></html>
"""


# ---------------------------------------------------------------------------
# _parse_price
# ---------------------------------------------------------------------------

class TestParsePrice:
    def test_simple_price(self):
        assert _parse_price("$950.00") == 950.0

    def test_price_range_takes_lower_bound(self):
        assert _parse_price("$900.00 to $1,050.00") == 900.0

    def test_price_with_commas(self):
        assert _parse_price("$1,100.00") == 1100.0

    def test_price_per_ea(self):
        assert _parse_price("$1,234.56/ea") == 1234.56

    def test_empty_returns_zero(self):
        assert _parse_price("") == 0.0


# ---------------------------------------------------------------------------
# _extract_seller_from_card
# ---------------------------------------------------------------------------

class TestExtractSellerFromCard:
    def _card(self, html: str):
        return BeautifulSoup(html, "lxml").select_one("li.s-card")

    def test_standard_card(self):
        card = self._card("""
        <li class="s-card" data-listingid="1">
          <span class="su-styled-text">techguy</span>
          <span class="su-styled-text">99.1% positive (1,234)</span>
        </li>""")
        username, count, ratio = _extract_seller_from_card(card)
        assert username == "techguy"
        assert count == 1234
        assert ratio == pytest.approx(0.991, abs=0.001)

    def test_new_account(self):
        card = self._card("""
        <li class="s-card" data-listingid="2">
          <span class="su-styled-text">new_user_2024</span>
          <span class="su-styled-text">100.0% positive (2)</span>
        </li>""")
        username, count, ratio = _extract_seller_from_card(card)
        assert username == "new_user_2024"
        assert count == 2
        assert ratio == pytest.approx(1.0, abs=0.001)

    def test_no_feedback_span_returns_empty(self):
        card = self._card("""
        <li class="s-card" data-listingid="3">
          <span class="su-styled-text">some_seller</span>
        </li>""")
        username, count, ratio = _extract_seller_from_card(card)
        assert username == ""
        assert count == 0
        assert ratio == 0.0


# ---------------------------------------------------------------------------
# _parse_time_left
# ---------------------------------------------------------------------------

class TestParseTimeLeft:
    def test_days_and_hours(self):
        assert _parse_time_left("3d 14h left") == timedelta(days=3, hours=14)

    def test_hours_and_minutes(self):
        assert _parse_time_left("14h 23m left") == timedelta(hours=14, minutes=23)

    def test_minutes_and_seconds(self):
        assert _parse_time_left("23m 45s left") == timedelta(minutes=23, seconds=45)

    def test_days_only(self):
        assert _parse_time_left("2d left") == timedelta(days=2)

    def test_no_match_returns_none(self):
        assert _parse_time_left("Buy It Now") is None

    def test_empty_returns_none(self):
        assert _parse_time_left("") is None

    def test_all_zeros_returns_none(self):
        assert _parse_time_left("0d 0h 0m 0s left") is None


# ---------------------------------------------------------------------------
# scrape_listings
# ---------------------------------------------------------------------------

class TestScrapeListings:
    def test_skips_promo_without_listingid(self):
        listings = scrape_listings(_EBAY_HTML)
        titles = [l.title for l in listings]
        assert "Shop on eBay" not in titles

    def test_parses_three_real_listings(self):
        assert len(scrape_listings(_EBAY_HTML)) == 3

    def test_platform_listing_id_from_data_attribute(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].platform_listing_id == "123456789"
        assert listings[1].platform_listing_id == "987654321"
        assert listings[2].platform_listing_id == "555000111"

    def test_url_strips_query_string(self):
        listings = scrape_listings(_EBAY_HTML)
        assert "?" not in listings[0].url
        assert listings[0].url == "https://www.ebay.com/itm/123456789"

    def test_price_range_takes_lower(self):
        assert scrape_listings(_EBAY_HTML)[1].price == 1100.0

    def test_condition_extracted_and_lowercased(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].condition == "used"
        assert listings[1].condition == "new"

    def test_photo_prefers_data_src_over_src(self):
        # Listing 2 has data-src set, src is empty
        assert scrape_listings(_EBAY_HTML)[1].photo_urls == ["https://i.ebayimg.com/thumbs/2.jpg"]

    def test_photo_falls_back_to_src(self):
        assert scrape_listings(_EBAY_HTML)[0].photo_urls == ["https://i.ebayimg.com/thumbs/1.jpg"]

    def test_seller_platform_id_from_card(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].seller_platform_id == "techguy"
        assert listings[2].seller_platform_id == "new_user_2024"

    def test_platform_is_ebay(self):
        assert all(l.platform == "ebay" for l in scrape_listings(_EBAY_HTML))

    def test_currency_is_usd(self):
        assert all(l.currency == "USD" for l in scrape_listings(_EBAY_HTML))

    def test_fixed_price_no_ends_at(self):
        listings = scrape_listings(_EBAY_HTML)
        assert all(l.ends_at is None for l in listings)
        assert all(l.buying_format == "fixed_price" for l in listings)

    def test_auction_sets_buying_format_and_ends_at(self):
        listings = scrape_listings(_AUCTION_HTML)
        assert len(listings) == 1
        assert listings[0].buying_format == "auction"
        assert listings[0].ends_at is not None

    def test_empty_html_returns_empty_list(self):
        assert scrape_listings("<html><body></body></html>") == []


# ---------------------------------------------------------------------------
# scrape_sellers
# ---------------------------------------------------------------------------

class TestScrapeSellers:
    def test_extracts_three_sellers(self):
        assert len(scrape_sellers(_EBAY_HTML)) == 3

    def test_feedback_count_and_ratio(self):
        sellers = scrape_sellers(_EBAY_HTML)
        assert sellers["techguy"].feedback_count == 1234
        assert sellers["techguy"].feedback_ratio == pytest.approx(0.991, abs=0.001)

    def test_deduplicates_sellers(self):
        # Same seller appearing in two cards should only produce one Seller object
        html = """<html><body><ul>
          <li class="s-card" data-listingid="1">
            <div class="s-card__title">Item A</div>
            <a class="s-card__link" href="https://www.ebay.com/itm/1"></a>
            <span class="su-styled-text">repeatguy</span>
            <span class="su-styled-text">99.0% positive (500)</span>
          </li>
          <li class="s-card" data-listingid="2">
            <div class="s-card__title">Item B</div>
            <a class="s-card__link" href="https://www.ebay.com/itm/2"></a>
            <span class="su-styled-text">repeatguy</span>
            <span class="su-styled-text">99.0% positive (500)</span>
          </li>
        </ul></body></html>"""
        sellers = scrape_sellers(html)
        assert len(sellers) == 1
        assert "repeatguy" in sellers

    def test_account_age_always_zero(self):
        """account_age_days is 0 from scraper — causes score_is_partial=True."""
        sellers = scrape_sellers(_EBAY_HTML)
        assert all(s.account_age_days == 0 for s in sellers.values())

    def test_category_history_always_empty(self):
        """category_history_json is '{}' from scraper — causes score_is_partial=True."""
        sellers = scrape_sellers(_EBAY_HTML)
        assert all(s.category_history_json == "{}" for s in sellers.values())

    def test_platform_is_ebay(self):
        sellers = scrape_sellers(_EBAY_HTML)
        assert all(s.platform == "ebay" for s in sellers.values())
