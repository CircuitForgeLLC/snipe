import pytest

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
