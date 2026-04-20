import pytest

from api.main import _extract_ebay_item_id
from app.platforms.ebay.normaliser import normalise_listing, normalise_seller


def test_normalise_listing_maps_fields():
    raw = {
        "itemId": "v1|12345|0",
        "title": "RTX 4090 GPU",
        "price": {"value": "950.00", "currency": "USD"},
        "condition": "USED",
        "seller": {"username": "techguy", "feedbackScore": 300, "feedbackPercentage": "99.1"},
        "itemWebUrl": "https://ebay.com/itm/12345",
        "image": {"imageUrl": "https://i.ebayimg.com/1.jpg"},
        "additionalImages": [{"imageUrl": "https://i.ebayimg.com/2.jpg"}],
        "itemCreationDate": "2026-03-20T00:00:00.000Z",
    }
    listing = normalise_listing(raw)
    assert listing.platform == "ebay"
    assert listing.platform_listing_id == "v1|12345|0"
    assert listing.title == "RTX 4090 GPU"
    assert listing.price == 950.0
    assert listing.condition == "used"
    assert listing.seller_platform_id == "techguy"
    assert "https://i.ebayimg.com/1.jpg" in listing.photo_urls
    assert "https://i.ebayimg.com/2.jpg" in listing.photo_urls


def test_normalise_listing_handles_missing_images():
    raw = {
        "itemId": "v1|999|0",
        "title": "GPU",
        "price": {"value": "100.00", "currency": "USD"},
        "condition": "NEW",
        "seller": {"username": "u"},
        "itemWebUrl": "https://ebay.com/itm/999",
    }
    listing = normalise_listing(raw)
    assert listing.photo_urls == []


def test_normalise_seller_maps_fields():
    raw = {
        "username": "techguy",
        "feedbackScore": 300,
        "feedbackPercentage": "99.1",
        "registrationDate": "2020-03-01T00:00:00.000Z",
        "sellerFeedbackSummary": {
            "feedbackByCategory": [
                {"transactionPercent": "95.0", "categorySite": "ELECTRONICS", "count": "50"}
            ]
        }
    }
    seller = normalise_seller(raw)
    assert seller.username == "techguy"
    assert seller.feedback_count == 300
    assert seller.feedback_ratio == pytest.approx(0.991, abs=0.001)
    assert seller.account_age_days > 0


# ── _extract_ebay_item_id ─────────────────────────────────────────────────────

class TestExtractEbayItemId:
    """Unit tests for the URL-to-item-ID normaliser."""

    def test_itm_url_with_title_slug(self):
        url = "https://www.ebay.com/itm/Sony-WH-1000XM5-Headphones/123456789012"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_itm_url_without_title_slug(self):
        url = "https://www.ebay.com/itm/123456789012"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_itm_url_no_www(self):
        url = "https://ebay.com/itm/123456789012"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_itm_url_with_query_params(self):
        url = "https://www.ebay.com/itm/123456789012?hash=item1234abcd"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_pay_ebay_rxo_with_itemId_query_param(self):
        url = "https://pay.ebay.com/rxo?action=view&sessionid=abc123&itemId=123456789012"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_pay_ebay_rxo_path_with_itemId(self):
        url = "https://pay.ebay.com/rxo/view?itemId=123456789012"
        assert _extract_ebay_item_id(url) == "123456789012"

    def test_non_ebay_url_returns_none(self):
        assert _extract_ebay_item_id("https://amazon.com/dp/B08N5WRWNW") is None

    def test_plain_keyword_returns_none(self):
        assert _extract_ebay_item_id("rtx 4090 gpu") is None

    def test_empty_string_returns_none(self):
        assert _extract_ebay_item_id("") is None

    def test_ebay_url_no_item_id_returns_none(self):
        assert _extract_ebay_item_id("https://www.ebay.com/sch/i.html?_nkw=gpu") is None

    def test_pay_ebay_no_item_id_returns_none(self):
        assert _extract_ebay_item_id("https://pay.ebay.com/rxo?action=view&sessionid=abc") is None
