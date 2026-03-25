"""Tests for the scraper-based eBay adapter.

Uses a minimal HTML fixture that mirrors eBay's search results structure.
No HTTP requests are made — all tests operate on the pure parsing functions.
"""
import pytest
from app.platforms.ebay.scraper import scrape_listings, scrape_sellers, _parse_price, _parse_seller

# ---------------------------------------------------------------------------
# Minimal eBay search results HTML fixture
# ---------------------------------------------------------------------------

_EBAY_HTML = """
<html><body>
<ul class="srp-results">
  <!-- eBay injects this ghost item first — should be skipped -->
  <li class="s-item">
    <div class="s-item__title"><span>Shop on eBay</span></div>
    <a class="s-item__link" href="https://ebay.com/shop"></a>
  </li>

  <!-- Real listing 1: established seller, normal price -->
  <li class="s-item">
    <h3 class="s-item__title"><span>RTX 4090 Founders Edition GPU</span></h3>
    <a class="s-item__link" href="https://www.ebay.com/itm/123456789"></a>
    <span class="s-item__price">$950.00</span>
    <span class="SECONDARY_INFO">Used</span>
    <div class="s-item__image-wrapper"><img src="https://i.ebayimg.com/thumbs/1.jpg"/></div>
    <span class="s-item__seller-info-text">techguy (1,234) 99.1% positive feedback</span>
  </li>

  <!-- Real listing 2: price range, new condition -->
  <li class="s-item">
    <h3 class="s-item__title"><span>RTX 4090 Gaming OC 24GB</span></h3>
    <a class="s-item__link" href="https://www.ebay.com/itm/987654321"></a>
    <span class="s-item__price">$1,100.00 to $1,200.00</span>
    <span class="SECONDARY_INFO">New</span>
    <div class="s-item__image-wrapper"><img data-src="https://i.ebayimg.com/thumbs/2.jpg" src=""/></div>
    <span class="s-item__seller-info-text">gpu_warehouse (450) 98.7% positive feedback</span>
  </li>

  <!-- Real listing 3: low feedback seller, suspicious price -->
  <li class="s-item">
    <h3 class="s-item__title"><span>RTX 4090 BNIB Sealed</span></h3>
    <a class="s-item__link" href="https://www.ebay.com/itm/555000111"></a>
    <span class="s-item__price">$499.00</span>
    <span class="SECONDARY_INFO">New</span>
    <div class="s-item__image-wrapper"><img src="https://i.ebayimg.com/thumbs/3.jpg"/></div>
    <span class="s-item__seller-info-text">new_user_2024 (2) 100.0% positive feedback</span>
  </li>
</ul>
</body></html>
"""


# ---------------------------------------------------------------------------
# Unit tests: pure parsing functions
# ---------------------------------------------------------------------------

class TestParsePrice:
    def test_simple_price(self):
        assert _parse_price("$950.00") == 950.0

    def test_price_range_takes_lower_bound(self):
        assert _parse_price("$900.00 to $1,050.00") == 900.0

    def test_price_with_commas(self):
        assert _parse_price("$1,100.00") == 1100.0

    def test_empty_returns_zero(self):
        assert _parse_price("") == 0.0


class TestParseSeller:
    def test_standard_format(self):
        username, count, ratio = _parse_seller("techguy (1,234) 99.1% positive feedback")
        assert username == "techguy"
        assert count == 1234
        assert ratio == pytest.approx(0.991, abs=0.001)

    def test_low_count(self):
        username, count, ratio = _parse_seller("new_user_2024 (2) 100.0% positive feedback")
        assert username == "new_user_2024"
        assert count == 2
        assert ratio == pytest.approx(1.0, abs=0.001)

    def test_fallback_on_malformed(self):
        username, count, ratio = _parse_seller("weirdformat")
        assert username == "weirdformat"
        assert count == 0
        assert ratio == 0.0


# ---------------------------------------------------------------------------
# Integration tests: HTML fixture → domain objects
# ---------------------------------------------------------------------------

class TestScrapeListings:
    def test_skips_shop_on_ebay_ghost(self):
        listings = scrape_listings(_EBAY_HTML)
        titles = [l.title for l in listings]
        assert all("Shop on eBay" not in t for t in titles)

    def test_parses_three_real_listings(self):
        listings = scrape_listings(_EBAY_HTML)
        assert len(listings) == 3

    def test_extracts_platform_listing_id_from_url(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].platform_listing_id == "123456789"
        assert listings[1].platform_listing_id == "987654321"

    def test_price_range_takes_lower(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[1].price == 1100.0

    def test_condition_lowercased(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].condition == "used"
        assert listings[1].condition == "new"

    def test_photo_prefers_data_src(self):
        listings = scrape_listings(_EBAY_HTML)
        # Listing 2 has data-src set, src empty
        assert listings[1].photo_urls == ["https://i.ebayimg.com/thumbs/2.jpg"]

    def test_seller_platform_id_set(self):
        listings = scrape_listings(_EBAY_HTML)
        assert listings[0].seller_platform_id == "techguy"
        assert listings[2].seller_platform_id == "new_user_2024"


class TestScrapeSellers:
    def test_extracts_three_sellers(self):
        sellers = scrape_sellers(_EBAY_HTML)
        assert len(sellers) == 3

    def test_feedback_count_and_ratio(self):
        sellers = scrape_sellers(_EBAY_HTML)
        assert sellers["techguy"].feedback_count == 1234
        assert sellers["techguy"].feedback_ratio == pytest.approx(0.991, abs=0.001)

    def test_account_age_is_zero(self):
        """account_age_days is always 0 from scraper — signals partial score."""
        sellers = scrape_sellers(_EBAY_HTML)
        assert all(s.account_age_days == 0 for s in sellers.values())

    def test_category_history_is_empty(self):
        """category_history_json is always '{}' from scraper — signals partial score."""
        sellers = scrape_sellers(_EBAY_HTML)
        assert all(s.category_history_json == "{}" for s in sellers.values())
