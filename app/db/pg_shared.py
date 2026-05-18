from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from app.db.models import MarketComp, Seller

log = logging.getLogger(__name__)

_MIN_CONN = 2
_MAX_CONN = 20


class SnipeSharedDB:
    """Thread-safe Postgres connection pool for Snipe shared tables."""

    def __init__(self, dsn: str) -> None:
        self._pool = ThreadedConnectionPool(_MIN_CONN, _MAX_CONN, dsn=dsn)

    def getconn(self):
        return self._pool.getconn()

    def putconn(self, conn) -> None:
        self._pool.putconn(conn)

    def close(self) -> None:
        self._pool.closeall()

    def run_migrations(self) -> None:
        """Apply pg_migrations/*.sql in filename order. Idempotent."""
        migrations_dir = Path(__file__).parent / "pg_migrations"
        files = sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)

        conn = self.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS _snipe_shared_migrations (
                        filename   TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                conn.commit()
                for f in files:
                    cur.execute(
                        "SELECT 1 FROM _snipe_shared_migrations WHERE filename = %s",
                        (f.name,),
                    )
                    if cur.fetchone():
                        continue
                    log.info("Applying migration: %s", f.name)
                    cur.execute(f.read_text())
                    cur.execute(
                        "INSERT INTO _snipe_shared_migrations (filename) VALUES (%s)",
                        (f.name,),
                    )
                    conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.putconn(conn)


class SnipeSharedStore:
    """Postgres-backed store for sellers, market_comps, and reported_sellers.

    Satisfies SharedTableProtocol. clone() returns self — ThreadedConnectionPool
    is already thread-safe, so no new instance is needed per thread.
    """

    def __init__(self, db: SnipeSharedDB) -> None:
        self._db = db

    def clone(self) -> "SnipeSharedStore":
        return self

    # Sellers

    def save_seller(self, seller: Seller) -> None:
        self.save_sellers([seller])

    def save_sellers(self, sellers: list[Seller]) -> None:
        if not sellers:
            return
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO sellers
                        (platform, platform_seller_id, username, account_age_days,
                         feedback_count, feedback_ratio, category_history_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (platform, platform_seller_id) DO UPDATE SET
                        username              = EXCLUDED.username,
                        feedback_count        = EXCLUDED.feedback_count,
                        feedback_ratio        = EXCLUDED.feedback_ratio,
                        account_age_days      = COALESCE(
                            EXCLUDED.account_age_days,
                            sellers.account_age_days
                        ),
                        category_history_json = COALESCE(
                            NULLIF(NULLIF(EXCLUDED.category_history_json, '{}'), ''),
                            NULLIF(NULLIF(sellers.category_history_json, '{}'), ''),
                            '{}'
                        ),
                        fetched_at = NOW()
                    """,
                    [
                        (s.platform, s.platform_seller_id, s.username, s.account_age_days,
                         s.feedback_count, s.feedback_ratio, s.category_history_json or "{}")
                        for s in sellers
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)

    def get_seller(self, platform: str, platform_seller_id: str) -> Optional[Seller]:
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT platform, platform_seller_id, username, account_age_days,
                           feedback_count, feedback_ratio, category_history_json,
                           id, fetched_at
                    FROM sellers
                    WHERE platform = %s AND platform_seller_id = %s
                    """,
                    (platform, platform_seller_id),
                )
                row = cur.fetchone()
            if not row:
                return None
            return Seller(*row[:7], id=row[7], fetched_at=str(row[8]))
        finally:
            self._db.putconn(conn)

    def delete_seller_data(self, platform: str, platform_seller_id: str) -> None:
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM sellers WHERE platform = %s AND platform_seller_id = %s",
                    (platform, platform_seller_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)

    # MarketComps

    def save_market_comp(self, comp: MarketComp) -> None:
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO market_comps
                        (platform, query_hash, median_price, sample_count, expires_at)
                    VALUES (%s, %s, %s, %s, %s::TIMESTAMPTZ)
                    ON CONFLICT (platform, query_hash) DO UPDATE SET
                        median_price = EXCLUDED.median_price,
                        sample_count = EXCLUDED.sample_count,
                        expires_at   = EXCLUDED.expires_at,
                        fetched_at   = NOW()
                    """,
                    (comp.platform, comp.query_hash, comp.median_price,
                     comp.sample_count, comp.expires_at),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)

    def get_market_comp(self, platform: str, query_hash: str) -> Optional[MarketComp]:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT platform, query_hash, median_price, sample_count,
                           expires_at, id, fetched_at
                    FROM market_comps
                    WHERE platform = %s AND query_hash = %s AND expires_at > %s::TIMESTAMPTZ
                    """,
                    (platform, query_hash, now),
                )
                row = cur.fetchone()
            if not row:
                return None
            return MarketComp(*row[:5], id=row[5], fetched_at=str(row[6]))
        finally:
            self._db.putconn(conn)

    # Reported Sellers

    def mark_reported(
        self,
        platform: str,
        platform_seller_id: str,
        username: Optional[str] = None,
        reported_by: str = "user",
    ) -> None:
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reported_sellers
                        (platform, platform_seller_id, username, reported_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (platform, platform_seller_id) DO NOTHING
                    """,
                    (platform, platform_seller_id, username, reported_by),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.putconn(conn)

    def list_reported(self, platform: str = "ebay") -> list[str]:
        conn = self._db.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT platform_seller_id FROM reported_sellers WHERE platform = %s",
                    (platform,),
                )
                return [row[0] for row in cur.fetchall()]
        finally:
            self._db.putconn(conn)
