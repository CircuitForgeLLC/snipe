"""Thin SQLite read/write layer for all Snipe models."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from circuitforge_core.db import get_connection, run_migrations

from .models import Listing, Seller, TrustScore, MarketComp, SavedSearch

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Store:
    def __init__(self, db_path: Path):
        self._conn = get_connection(db_path)
        run_migrations(self._conn, MIGRATIONS_DIR)

    # --- Seller ---

    def delete_seller_data(self, platform: str, platform_seller_id: str) -> None:
        """Permanently erase a seller and all their listings — GDPR/eBay deletion compliance."""
        self._conn.execute(
            "DELETE FROM sellers WHERE platform=? AND platform_seller_id=?",
            (platform, platform_seller_id),
        )
        self._conn.execute(
            "DELETE FROM listings WHERE platform=? AND seller_platform_id=?",
            (platform, platform_seller_id),
        )
        self._conn.commit()

    def save_seller(self, seller: Seller) -> None:
        self.save_sellers([seller])

    def save_sellers(self, sellers: list[Seller]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO sellers "
            "(platform, platform_seller_id, username, account_age_days, "
            "feedback_count, feedback_ratio, category_history_json) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (s.platform, s.platform_seller_id, s.username, s.account_age_days,
                 s.feedback_count, s.feedback_ratio, s.category_history_json)
                for s in sellers
            ],
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

    def refresh_seller_categories(
        self,
        platform: str,
        seller_ids: list[str],
        listing_store: "Optional[Store]" = None,
    ) -> int:
        """Derive category_history_json for sellers that lack it by aggregating
        their stored listings' category_name values.

        listing_store: the Store instance that holds listings (may differ from
        self in cloud split-DB mode where sellers live in shared.db and listings
        live in user.db). Defaults to self when not provided (local mode).

        Returns the count of sellers updated.
        """
        from app.platforms.ebay.scraper import _classify_category_label  # lazy to avoid circular

        src = listing_store if listing_store is not None else self

        if not seller_ids:
            return 0
        updated = 0
        for sid in seller_ids:
            seller = self.get_seller(platform, sid)
            if not seller or seller.category_history_json not in ("{}", "", None):
                continue  # already enriched
            rows = src._conn.execute(
                "SELECT category_name, COUNT(*) FROM listings "
                "WHERE platform=? AND seller_platform_id=? AND category_name IS NOT NULL "
                "GROUP BY category_name",
                (platform, sid),
            ).fetchall()
            if not rows:
                continue
            counts: dict[str, int] = {}
            for cat_name, cnt in rows:
                key = _classify_category_label(cat_name)
                if key:
                    counts[key] = counts.get(key, 0) + cnt
            if counts:
                from dataclasses import replace
                updated_seller = replace(seller, category_history_json=json.dumps(counts))
                self.save_seller(updated_seller)
                updated += 1
        return updated

    # --- Listing ---

    def save_listing(self, listing: Listing) -> None:
        self.save_listings([listing])

    def save_listings(self, listings: list[Listing]) -> None:
        """Upsert listings, preserving first_seen_at and price_at_first_seen on conflict.

        Uses INSERT ... ON CONFLICT DO UPDATE (SQLite 3.24+) so row IDs are stable
        across searches — trust_score FK references survive re-indexing.
        times_seen and last_seen_at accumulate on every sighting.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            """
            INSERT INTO listings
                (platform, platform_listing_id, title, price, currency, condition,
                 seller_platform_id, url, photo_urls, listing_age_days, buying_format,
                 ends_at, first_seen_at, last_seen_at, times_seen, price_at_first_seen,
                 category_name)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
            ON CONFLICT(platform, platform_listing_id) DO UPDATE SET
                title                = excluded.title,
                price                = excluded.price,
                condition            = excluded.condition,
                seller_platform_id   = excluded.seller_platform_id,
                url                  = excluded.url,
                photo_urls           = excluded.photo_urls,
                listing_age_days     = excluded.listing_age_days,
                buying_format        = excluded.buying_format,
                ends_at              = excluded.ends_at,
                last_seen_at         = excluded.last_seen_at,
                times_seen           = times_seen + 1,
                category_name        = COALESCE(excluded.category_name, category_name)
                -- first_seen_at and price_at_first_seen intentionally preserved
            """,
            [
                (l.platform, l.platform_listing_id, l.title, l.price, l.currency,
                 l.condition, l.seller_platform_id, l.url,
                 json.dumps(l.photo_urls), l.listing_age_days, l.buying_format, l.ends_at,
                 now, now, l.price, l.category_name)
                for l in listings
            ],
        )
        # Record price snapshots — INSERT OR IGNORE means only price changes land
        self._conn.executemany(
            """
            INSERT OR IGNORE INTO listing_price_history (listing_id, price, captured_at)
            SELECT id, ?, ? FROM listings
            WHERE platform=? AND platform_listing_id=?
            """,
            [
                (l.price, now, l.platform, l.platform_listing_id)
                for l in listings
            ],
        )
        self._conn.commit()

    def get_listings_staged(self, platform: str, platform_listing_ids: list[str]) -> dict[str, "Listing"]:
        """Bulk fetch listings by platform_listing_id, returning staging fields.

        Returns a dict keyed by platform_listing_id. Used to hydrate freshly-normalised
        listing objects after save_listings() so trust scoring sees times_seen,
        first_seen_at, price_at_first_seen, and the DB-assigned id.
        """
        if not platform_listing_ids:
            return {}
        placeholders = ",".join("?" * len(platform_listing_ids))
        rows = self._conn.execute(
            f"SELECT platform, platform_listing_id, title, price, currency, condition, "
            f"seller_platform_id, url, photo_urls, listing_age_days, id, fetched_at, "
            f"buying_format, ends_at, first_seen_at, last_seen_at, times_seen, price_at_first_seen, "
            f"category_name "
            f"FROM listings WHERE platform=? AND platform_listing_id IN ({placeholders})",
            [platform] + list(platform_listing_ids),
        ).fetchall()
        result: dict[str, Listing] = {}
        for row in rows:
            pid = row[1]
            result[pid] = Listing(
                *row[:8],
                photo_urls=json.loads(row[8]),
                listing_age_days=row[9],
                id=row[10],
                fetched_at=row[11],
                buying_format=row[12] or "fixed_price",
                ends_at=row[13],
                first_seen_at=row[14],
                last_seen_at=row[15],
                times_seen=row[16] or 1,
                price_at_first_seen=row[17],
                category_name=row[18],
            )
        return result

    def get_listing(self, platform: str, platform_listing_id: str) -> Optional[Listing]:
        row = self._conn.execute(
            "SELECT platform, platform_listing_id, title, price, currency, condition, "
            "seller_platform_id, url, photo_urls, listing_age_days, id, fetched_at, "
            "buying_format, ends_at, first_seen_at, last_seen_at, times_seen, price_at_first_seen "
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
            first_seen_at=row[14],
            last_seen_at=row[15],
            times_seen=row[16] or 1,
            price_at_first_seen=row[17],
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

    # --- SavedSearch ---

    def save_saved_search(self, s: SavedSearch) -> SavedSearch:
        cur = self._conn.execute(
            "INSERT INTO saved_searches (name, query, platform, filters_json) VALUES (?,?,?,?)",
            (s.name, s.query, s.platform, s.filters_json),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, created_at FROM saved_searches WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return SavedSearch(
            name=s.name, query=s.query, platform=s.platform,
            filters_json=s.filters_json, id=row[0], created_at=row[1],
        )

    def list_saved_searches(self) -> list[SavedSearch]:
        rows = self._conn.execute(
            "SELECT name, query, platform, filters_json, id, created_at, last_run_at "
            "FROM saved_searches ORDER BY created_at DESC"
        ).fetchall()
        return [
            SavedSearch(name=r[0], query=r[1], platform=r[2], filters_json=r[3],
                        id=r[4], created_at=r[5], last_run_at=r[6])
            for r in rows
        ]

    def delete_saved_search(self, saved_id: int) -> None:
        self._conn.execute("DELETE FROM saved_searches WHERE id=?", (saved_id,))
        self._conn.commit()

    def update_saved_search_last_run(self, saved_id: int) -> None:
        self._conn.execute(
            "UPDATE saved_searches SET last_run_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), saved_id),
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
