"""Thin SQLite read/write layer for all Snipe models."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from circuitforge_core.db import get_connection, run_migrations

from .models import Listing, Seller, TrustScore, MarketComp

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Store:
    def __init__(self, db_path: Path):
        self._conn = get_connection(db_path)
        run_migrations(self._conn, MIGRATIONS_DIR)

    # --- Seller ---

    def save_seller(self, seller: Seller) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sellers "
            "(platform, platform_seller_id, username, account_age_days, "
            "feedback_count, feedback_ratio, category_history_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (seller.platform, seller.platform_seller_id, seller.username,
             seller.account_age_days, seller.feedback_count, seller.feedback_ratio,
             seller.category_history_json),
        )
        self._conn.commit()

    def get_seller(self, platform: str, platform_seller_id: str) -> Optional[Seller]:
        row = self._conn.execute(
            "SELECT platform, platform_seller_id, username, account_age_days, "
            "feedback_count, feedback_ratio, category_history_json, id, fetched_at "
            "FROM sellers WHERE platform=? AND platform_seller_id=?",
            (platform, platform_seller_id),
        ).fetchone()
        if not row:
            return None
        return Seller(*row[:7], id=row[7], fetched_at=row[8])

    # --- Listing ---

    def save_listing(self, listing: Listing) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO listings "
            "(platform, platform_listing_id, title, price, currency, condition, "
            "seller_platform_id, url, photo_urls, listing_age_days, buying_format, ends_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (listing.platform, listing.platform_listing_id, listing.title,
             listing.price, listing.currency, listing.condition,
             listing.seller_platform_id, listing.url,
             json.dumps(listing.photo_urls), listing.listing_age_days,
             listing.buying_format, listing.ends_at),
        )
        self._conn.commit()

    def get_listing(self, platform: str, platform_listing_id: str) -> Optional[Listing]:
        row = self._conn.execute(
            "SELECT platform, platform_listing_id, title, price, currency, condition, "
            "seller_platform_id, url, photo_urls, listing_age_days, id, fetched_at, "
            "buying_format, ends_at "
            "FROM listings WHERE platform=? AND platform_listing_id=?",
            (platform, platform_listing_id),
        ).fetchone()
        if not row:
            return None
        return Listing(
            *row[:8],
            photo_urls=json.loads(row[8]),
            listing_age_days=row[9],
            id=row[10],
            fetched_at=row[11],
            buying_format=row[12] or "fixed_price",
            ends_at=row[13],
        )

    # --- MarketComp ---

    def save_market_comp(self, comp: MarketComp) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO market_comps "
            "(platform, query_hash, median_price, sample_count, expires_at) "
            "VALUES (?,?,?,?,?)",
            (comp.platform, comp.query_hash, comp.median_price,
             comp.sample_count, comp.expires_at),
        )
        self._conn.commit()

    def get_market_comp(self, platform: str, query_hash: str) -> Optional[MarketComp]:
        row = self._conn.execute(
            "SELECT platform, query_hash, median_price, sample_count, expires_at, id, fetched_at "
            "FROM market_comps WHERE platform=? AND query_hash=? AND expires_at > ?",
            (platform, query_hash, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
        if not row:
            return None
        return MarketComp(*row[:5], id=row[5], fetched_at=row[6])
