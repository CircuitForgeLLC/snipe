"""Thin SQLite read/write layer for all Snipe models."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from circuitforge_core.db import get_connection, run_migrations

from .models import Listing, MarketComp, SavedSearch, ScammerEntry, Seller, TrustScore, WatchAlert

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Store:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn = get_connection(db_path)
        run_migrations(self._conn, MIGRATIONS_DIR)
        # WAL mode: allows concurrent readers + one writer without blocking
        self._conn.execute("PRAGMA journal_mode=WAL")

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
        # COALESCE preserves enriched signals (account_age_days, category_history_json)
        # that were filled by BTF / _ssn passes — never overwrite with NULL from a
        # fresh search page that doesn't carry those signals.
        self._conn.executemany(
            "INSERT INTO sellers "
            "(platform, platform_seller_id, username, account_age_days, "
            "feedback_count, feedback_ratio, category_history_json) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(platform, platform_seller_id) DO UPDATE SET "
            "  username             = excluded.username, "
            "  feedback_count       = excluded.feedback_count, "
            "  feedback_ratio       = excluded.feedback_ratio, "
            "  account_age_days     = COALESCE(excluded.account_age_days, sellers.account_age_days), "
            "  category_history_json = COALESCE("
            "    CASE WHEN excluded.category_history_json IN ('{}', '', NULL) THEN NULL "
            "         ELSE excluded.category_history_json END, "
            "    CASE WHEN sellers.category_history_json IN ('{}', '', NULL) THEN NULL "
            "         ELSE sellers.category_history_json END, "
            "    '{}'"
            "  )",
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

    # --- TrustScore ---

    def save_trust_scores(self, scores: list[TrustScore]) -> None:
        """Upsert trust scores keyed by listing_id.

        photo_analysis_json is preserved on conflict so background vision
        results written by the task runner are never overwritten by a re-score.
        Requires idx_trust_scores_listing UNIQUE index (migration 007).
        """
        self._conn.executemany(
            "INSERT INTO trust_scores "
            "(listing_id, composite_score, account_age_score, feedback_count_score, "
            "feedback_ratio_score, price_vs_market_score, category_history_score, "
            "photo_hash_duplicate, red_flags_json, score_is_partial) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(listing_id) DO UPDATE SET "
            "  composite_score       = excluded.composite_score, "
            "  account_age_score     = excluded.account_age_score, "
            "  feedback_count_score  = excluded.feedback_count_score, "
            "  feedback_ratio_score  = excluded.feedback_ratio_score, "
            "  price_vs_market_score = excluded.price_vs_market_score, "
            "  category_history_score= excluded.category_history_score, "
            "  photo_hash_duplicate  = excluded.photo_hash_duplicate, "
            "  red_flags_json        = excluded.red_flags_json, "
            "  score_is_partial      = excluded.score_is_partial, "
            "  scored_at             = CURRENT_TIMESTAMP",
            # photo_analysis_json intentionally omitted — runner owns that column
            [
                (s.listing_id, s.composite_score, s.account_age_score,
                 s.feedback_count_score, s.feedback_ratio_score,
                 s.price_vs_market_score, s.category_history_score,
                 int(s.photo_hash_duplicate), s.red_flags_json, int(s.score_is_partial))
                for s in scores if s.listing_id
            ],
        )
        self._conn.commit()

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
            "SELECT name, query, platform, filters_json, id, created_at, last_run_at, "
            "monitor_enabled, poll_interval_min, min_trust_score, last_checked_at "
            "FROM saved_searches ORDER BY created_at DESC"
        ).fetchall()
        return [
            SavedSearch(
                name=r[0], query=r[1], platform=r[2], filters_json=r[3],
                id=r[4], created_at=r[5], last_run_at=r[6],
                monitor_enabled=bool(r[7]), poll_interval_min=r[8],
                min_trust_score=r[9], last_checked_at=r[10],
            )
            for r in rows
        ]

    def update_monitor_settings(
        self,
        saved_id: int,
        *,
        monitor_enabled: bool,
        poll_interval_min: int,
        min_trust_score: int,
    ) -> None:
        self._conn.execute(
            "UPDATE saved_searches "
            "SET monitor_enabled=?, poll_interval_min=?, min_trust_score=? "
            "WHERE id=?",
            (int(monitor_enabled), poll_interval_min, min_trust_score, saved_id),
        )
        self._conn.commit()

    def list_monitored_searches(self) -> list[SavedSearch]:
        """Return all saved searches with monitoring enabled (used by background poller)."""
        rows = self._conn.execute(
            "SELECT name, query, platform, filters_json, id, created_at, last_run_at, "
            "monitor_enabled, poll_interval_min, min_trust_score, last_checked_at "
            "FROM saved_searches WHERE monitor_enabled=1"
        ).fetchall()
        return [
            SavedSearch(
                name=r[0], query=r[1], platform=r[2], filters_json=r[3],
                id=r[4], created_at=r[5], last_run_at=r[6],
                monitor_enabled=True, poll_interval_min=r[8],
                min_trust_score=r[9], last_checked_at=r[10],
            )
            for r in rows
        ]

    def mark_search_checked(self, saved_id: int) -> None:
        self._conn.execute(
            "UPDATE saved_searches SET last_checked_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), saved_id),
        )
        self._conn.commit()

    def count_active_monitors(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM saved_searches WHERE monitor_enabled=1"
        ).fetchone()
        return row[0] if row else 0

    def delete_saved_search(self, saved_id: int) -> None:
        self._conn.execute("DELETE FROM saved_searches WHERE id=?", (saved_id,))
        self._conn.commit()

    def update_saved_search_last_run(self, saved_id: int) -> None:
        self._conn.execute(
            "UPDATE saved_searches SET last_run_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), saved_id),
        )
        self._conn.commit()

    # --- WatchAlerts ---

    def upsert_alert(self, alert: WatchAlert) -> tuple[int, bool]:
        """Insert alert if not already present. Returns (id, is_new)."""
        existing = self._conn.execute(
            "SELECT id FROM watch_alerts WHERE saved_search_id=? AND platform_listing_id=?",
            (alert.saved_search_id, alert.platform_listing_id),
        ).fetchone()
        if existing:
            return existing[0], False
        cur = self._conn.execute(
            "INSERT INTO watch_alerts "
            "(saved_search_id, platform_listing_id, title, price, currency, trust_score, url) "
            "VALUES (?,?,?,?,?,?,?)",
            (alert.saved_search_id, alert.platform_listing_id, alert.title,
             alert.price, alert.currency, alert.trust_score, alert.url),
        )
        self._conn.commit()
        return cur.lastrowid, True

    def list_alerts(self, *, include_dismissed: bool = False) -> list[WatchAlert]:
        where = "" if include_dismissed else "WHERE dismissed_at IS NULL"
        rows = self._conn.execute(
            f"SELECT id, saved_search_id, platform_listing_id, title, price, currency, "
            f"trust_score, url, first_alerted_at, dismissed_at "
            f"FROM watch_alerts {where} ORDER BY first_alerted_at DESC"
        ).fetchall()
        return [
            WatchAlert(
                id=r[0], saved_search_id=r[1], platform_listing_id=r[2],
                title=r[3], price=r[4], currency=r[5], trust_score=r[6],
                url=r[7], first_alerted_at=r[8], dismissed_at=r[9],
            )
            for r in rows
        ]

    def count_undismissed_alerts(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM watch_alerts WHERE dismissed_at IS NULL"
        ).fetchone()
        return row[0] if row else 0

    def dismiss_alert(self, alert_id: int) -> None:
        self._conn.execute(
            "UPDATE watch_alerts SET dismissed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), alert_id),
        )
        self._conn.commit()

    def dismiss_all_alerts(self) -> int:
        """Dismiss all undismissed alerts. Returns count dismissed."""
        cur = self._conn.execute(
            "UPDATE watch_alerts SET dismissed_at=? WHERE dismissed_at IS NULL",
            (datetime.now(timezone.utc).isoformat(),),
        )
        self._conn.commit()
        return cur.rowcount

    # --- ActiveMonitors (sched_db / shared_db) ---

    def upsert_active_monitor(
        self,
        user_db_path: str,
        saved_search_id: int,
        poll_interval_min: int,
    ) -> None:
        """Register or update a monitor in the cross-user registry (sched_db)."""
        self._conn.execute(
            "INSERT INTO active_monitors (user_db_path, saved_search_id, poll_interval_min) "
            "VALUES (?,?,?) "
            "ON CONFLICT(user_db_path, saved_search_id) DO UPDATE SET "
            "  poll_interval_min=excluded.poll_interval_min",
            (user_db_path, saved_search_id, poll_interval_min),
        )
        self._conn.commit()

    def remove_active_monitor(self, user_db_path: str, saved_search_id: int) -> None:
        self._conn.execute(
            "DELETE FROM active_monitors WHERE user_db_path=? AND saved_search_id=?",
            (user_db_path, saved_search_id),
        )
        self._conn.commit()

    def list_due_active_monitors(self) -> list[tuple[str, int, int]]:
        """Return (user_db_path, saved_search_id, poll_interval_min) for monitors that are due.

        Due = never checked OR last_checked_at is old enough given poll_interval_min.
        Uses SQLite's strftime('%s') for epoch arithmetic without Python datetime overhead.
        """
        rows = self._conn.execute(
            "SELECT user_db_path, saved_search_id, poll_interval_min "
            "FROM active_monitors "
            "WHERE last_checked_at IS NULL "
            "   OR (strftime('%s','now') - strftime('%s', last_checked_at)) "
            "       >= poll_interval_min * 60"
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def mark_active_monitor_checked(self, user_db_path: str, saved_search_id: int) -> None:
        self._conn.execute(
            "UPDATE active_monitors SET last_checked_at=? "
            "WHERE user_db_path=? AND saved_search_id=?",
            (datetime.now(timezone.utc).isoformat(), user_db_path, saved_search_id),
        )
        self._conn.commit()

    # --- ScammerBlocklist ---

    def add_to_blocklist(self, entry: ScammerEntry) -> ScammerEntry:
        """Upsert a seller into the blocklist. Returns the saved entry with id and created_at."""
        self._conn.execute(
            "INSERT INTO scammer_blocklist "
            "(platform, platform_seller_id, username, reason, source) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(platform, platform_seller_id) DO UPDATE SET "
            "  username = excluded.username, "
            "  reason   = COALESCE(excluded.reason, scammer_blocklist.reason), "
            "  source   = excluded.source",
            (entry.platform, entry.platform_seller_id, entry.username,
             entry.reason, entry.source),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, created_at FROM scammer_blocklist "
            "WHERE platform=? AND platform_seller_id=?",
            (entry.platform, entry.platform_seller_id),
        ).fetchone()
        from dataclasses import replace
        return replace(entry, id=row[0], created_at=row[1])

    def remove_from_blocklist(self, platform: str, platform_seller_id: str) -> None:
        self._conn.execute(
            "DELETE FROM scammer_blocklist WHERE platform=? AND platform_seller_id=?",
            (platform, platform_seller_id),
        )
        self._conn.commit()

    def is_blocklisted(self, platform: str, platform_seller_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM scammer_blocklist WHERE platform=? AND platform_seller_id=? LIMIT 1",
            (platform, platform_seller_id),
        ).fetchone()
        return row is not None

    def list_blocklist(self, platform: str = "ebay") -> list[ScammerEntry]:
        rows = self._conn.execute(
            "SELECT platform, platform_seller_id, username, reason, source, id, created_at "
            "FROM scammer_blocklist WHERE platform=? ORDER BY created_at DESC",
            (platform,),
        ).fetchall()
        return [
            ScammerEntry(
                platform=r[0], platform_seller_id=r[1], username=r[2],
                reason=r[3], source=r[4], id=r[5], created_at=r[6],
            )
            for r in rows
        ]

    # --- Reported Sellers ---

    def mark_reported(
        self,
        platform: str,
        platform_seller_id: str,
        username: Optional[str] = None,
        reported_by: str = "user",
    ) -> None:
        """Record that the user has filed an eBay T&S report for this seller.

        Uses IGNORE on conflict so the first-report timestamp is preserved.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO reported_sellers "
            "(platform, platform_seller_id, username, reported_by) "
            "VALUES (?,?,?,?)",
            (platform, platform_seller_id, username, reported_by),
        )
        self._conn.commit()

    def list_reported(self, platform: str = "ebay") -> list[str]:
        """Return all platform_seller_ids that have been reported."""
        rows = self._conn.execute(
            "SELECT platform_seller_id FROM reported_sellers WHERE platform=?",
            (platform,),
        ).fetchall()
        return [r[0] for r in rows]

    def save_community_signal(self, seller_id: str, confirmed: bool) -> None:
        """Record a user's trust-score feedback signal into the shared DB."""
        self._conn.execute(
            "INSERT INTO community_signals (seller_id, confirmed) VALUES (?, ?)",
            (seller_id, 1 if confirmed else 0),
        )
        self._conn.commit()

    # --- User Preferences ---

    def get_user_preference(self, path: str, default=None):
        """Read a preference value at dot-separated path (e.g. 'affiliate.opt_out').

        Reads from the singleton user_preferences row; returns *default* if the
        table is empty or the path is not set.
        """
        from circuitforge_core.preferences.paths import get_path
        row = self._conn.execute(
            "SELECT prefs_json FROM user_preferences WHERE id=1"
        ).fetchone()
        if not row:
            return default
        return get_path(json.loads(row[0]), path, default=default)

    def set_user_preference(self, path: str, value) -> None:
        """Write *value* at dot-separated path (immutable JSON update).

        Creates the singleton row on first write; merges subsequent updates
        so sibling paths are preserved.
        """
        from circuitforge_core.preferences.paths import set_path
        row = self._conn.execute(
            "SELECT prefs_json FROM user_preferences WHERE id=1"
        ).fetchone()
        prefs = json.loads(row[0]) if row else {}
        updated = set_path(prefs, path, value)
        self._conn.execute(
            "INSERT INTO user_preferences (id, prefs_json, updated_at) "
            "VALUES (1, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  prefs_json = excluded.prefs_json, "
            "  updated_at = excluded.updated_at",
            (json.dumps(updated),),
        )
        self._conn.commit()

    def get_all_preferences(self) -> dict:
        """Return all preferences as a plain dict (empty dict if not yet set)."""
        row = self._conn.execute(
            "SELECT prefs_json FROM user_preferences WHERE id=1"
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def get_market_comp(self, platform: str, query_hash: str) -> Optional[MarketComp]:
        row = self._conn.execute(
            "SELECT platform, query_hash, median_price, sample_count, expires_at, id, fetched_at "
            "FROM market_comps WHERE platform=? AND query_hash=? AND expires_at > ?",
            (platform, query_hash, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
        if not row:
            return None
        return MarketComp(*row[:5], id=row[5], fetched_at=row[6])
