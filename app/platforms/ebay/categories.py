# app/platforms/ebay/categories.py
# MIT License
"""eBay category cache — fetches leaf categories from the Taxonomy API and stores them
in the local SQLite DB for injection into LLM query-builder prompts.

Refreshed weekly. Falls back to a hardcoded bootstrap table when no eBay API
credentials are configured (scraper-only users still get usable category hints).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# Bootstrap table — common categories for self-hosters without eBay API credentials.
# category_id values are stable eBay leaf IDs (US marketplace, as of 2026).
_BOOTSTRAP_CATEGORIES: list[tuple[str, str, str]] = [
    ("27386", "Graphics Cards",     "Consumer Electronics > Computers > Components > Graphics/Video Cards"),
    ("164",   "CPUs/Processors",    "Consumer Electronics > Computers > Components > CPUs/Processors"),
    ("170083","RAM",                "Consumer Electronics > Computers > Components > Memory (RAM)"),
    ("175669","Solid State Drives", "Consumer Electronics > Computers > Components > Drives > Solid State Drives"),
    ("177089","Hard Drives",        "Consumer Electronics > Computers > Components > Drives > Hard Drives"),
    ("179142","Laptops",            "Consumer Electronics > Computers > Laptops & Netbooks"),
    ("171957","Desktop Computers",  "Consumer Electronics > Computers > Desktops & All-in-Ones"),
    ("293",   "Consumer Electronics","Consumer Electronics"),
    ("625",   "Cameras",            "Consumer Electronics > Cameras & Photography > Digital Cameras"),
    ("15052", "Vintage Cameras",    "Consumer Electronics > Cameras & Photography > Vintage Movie Cameras"),
    ("11724", "Audio Equipment",    "Consumer Electronics > TV, Video & Home Audio > Home Audio"),
    ("3676",  "Vinyl Records",      "Music > Records"),
    ("870",   "Musical Instruments","Musical Instruments & Gear"),
    ("31388", "Video Game Consoles","Video Games & Consoles > Video Game Consoles"),
    ("139971","Video Games",        "Video Games & Consoles > Video Games"),
    ("139973","Video Game Accessories", "Video Games & Consoles > Video Game Accessories"),
    ("14308", "Networking Gear",    "Computers/Tablets & Networking > Home Networking & Connectivity"),
    ("182062","Smartphones",        "Cell Phones & Smartphones"),
    ("9394",  "Tablets",            "Computers/Tablets & Networking > Tablets & eBook Readers"),
    ("11233", "Collectibles",       "Collectibles"),
]


class EbayCategoryCache:
    """Caches eBay leaf categories in SQLite for LLM prompt injection.

    Args:
        conn: An open sqlite3.Connection with migration 011 already applied.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def is_stale(self, max_age_days: int = 7) -> bool:
        """Return True if the cache is empty or all entries are older than max_age_days."""
        cur = self._conn.execute("SELECT MAX(refreshed_at) FROM ebay_categories")
        row = cur.fetchone()
        if not row or not row[0]:
            return True
        try:
            latest = datetime.fromisoformat(row[0])
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - latest > timedelta(days=max_age_days)
        except ValueError:
            return True

    def _seed_bootstrap(self) -> None:
        """Insert the hardcoded bootstrap categories. Idempotent (ON CONFLICT IGNORE)."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.executemany(
            "INSERT OR IGNORE INTO ebay_categories"
            " (category_id, name, full_path, is_leaf, refreshed_at)"
            " VALUES (?, ?, ?, 1, ?)",
            [(cid, name, path, now) for cid, name, path in _BOOTSTRAP_CATEGORIES],
        )
        self._conn.commit()
        log.info("EbayCategoryCache: seeded %d bootstrap categories.", len(_BOOTSTRAP_CATEGORIES))
