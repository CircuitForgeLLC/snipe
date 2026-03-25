"""Convert raw eBay API responses into Snipe domain objects."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from app.db.models import Listing, Seller


def normalise_listing(raw: dict) -> Listing:
    price_data = raw.get("price", {})
    photos = []
    if "image" in raw:
        photos.append(raw["image"].get("imageUrl", ""))
    for img in raw.get("additionalImages", []):
        url = img.get("imageUrl", "")
        if url and url not in photos:
            photos.append(url)
    photos = [p for p in photos if p]

    listing_age_days = 0
    created_raw = raw.get("itemCreationDate", "")
    if created_raw:
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            listing_age_days = (datetime.now(timezone.utc) - created).days
        except ValueError:
            pass

    seller = raw.get("seller", {})
    return Listing(
        platform="ebay",
        platform_listing_id=raw["itemId"],
        title=raw.get("title", ""),
        price=float(price_data.get("value", 0)),
        currency=price_data.get("currency", "USD"),
        condition=raw.get("condition", "").lower(),
        seller_platform_id=seller.get("username", ""),
        url=raw.get("itemWebUrl", ""),
        photo_urls=photos,
        listing_age_days=listing_age_days,
    )


def normalise_seller(raw: dict) -> Seller:
    feedback_pct = float(raw.get("feedbackPercentage", "0").strip("%")) / 100.0

    account_age_days = 0
    reg_date_raw = raw.get("registrationDate", "")
    if reg_date_raw:
        try:
            reg_date = datetime.fromisoformat(reg_date_raw.replace("Z", "+00:00"))
            account_age_days = (datetime.now(timezone.utc) - reg_date).days
        except ValueError:
            pass

    category_history = {}
    summary = raw.get("sellerFeedbackSummary", {})
    for entry in summary.get("feedbackByCategory", []):
        category_history[entry.get("categorySite", "")] = int(entry.get("count", 0))

    return Seller(
        platform="ebay",
        platform_seller_id=raw["username"],
        username=raw["username"],
        account_age_days=account_age_days,
        feedback_count=int(raw.get("feedbackScore", 0)),
        feedback_ratio=feedback_pct,
        category_history_json=json.dumps(category_history),
    )
