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

import requests

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

    def get_relevant(
        self,
        keywords: list[str],
        limit: int = 30,
    ) -> list[tuple[str, str]]:
        """Return (category_id, full_path) pairs matching any keyword.

        Matches against both name and full_path (case-insensitive LIKE).
        Returns at most `limit` rows.
        """
        if not keywords:
            return []
        conditions = " OR ".join(
            "LOWER(name) LIKE ? OR LOWER(full_path) LIKE ?" for _ in keywords
        )
        params: list[str] = []
        for kw in keywords:
            like = f"%{kw.lower()}%"
            params.extend([like, like])
        params.append(limit)
        cur = self._conn.execute(
            f"SELECT category_id, full_path FROM ebay_categories"
            f" WHERE {conditions} ORDER BY name LIMIT ?",
            params,
        )
        return [(row[0], row[1]) for row in cur.fetchall()]

    def get_all_for_prompt(self, limit: int = 80) -> list[tuple[str, str]]:
        """Return up to `limit` (category_id, full_path) pairs, sorted by name.

        Used when no keyword context is available.
        """
        cur = self._conn.execute(
            "SELECT category_id, full_path FROM ebay_categories ORDER BY name LIMIT ?",
            (limit,),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]

    def refresh(
        self,
        token_manager: Optional["EbayTokenManager"] = None,
    ) -> int:
        """Fetch the eBay category tree and upsert leaf nodes into SQLite.

        Args:
            token_manager: An `EbayTokenManager` instance for the Taxonomy API.
                If None, falls back to seeding the hardcoded bootstrap table.

        Returns:
            Number of leaf categories stored.
        """
        if token_manager is None:
            self._seed_bootstrap()
            cur = self._conn.execute("SELECT COUNT(*) FROM ebay_categories")
            return cur.fetchone()[0]

        try:
            token = token_manager.get_token()
            headers = {"Authorization": f"Bearer {token}"}

            # Step 1: get default tree ID for EBAY_US
            id_resp = requests.get(
                "https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id",
                params={"marketplace_id": "EBAY_US"},
                headers=headers,
                timeout=30,
            )
            id_resp.raise_for_status()
            tree_id = id_resp.json()["categoryTreeId"]

            # Step 2: fetch full tree (large response — may take several seconds)
            tree_resp = requests.get(
                f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{tree_id}",
                headers=headers,
                timeout=120,
            )
            tree_resp.raise_for_status()
            tree = tree_resp.json()

            leaves: list[tuple[str, str, str]] = []
            _extract_leaves(tree["rootCategoryNode"], path="", leaves=leaves)

            now = datetime.now(timezone.utc).isoformat()
            self._conn.executemany(
                "INSERT OR REPLACE INTO ebay_categories"
                " (category_id, name, full_path, is_leaf, refreshed_at)"
                " VALUES (?, ?, ?, 1, ?)",
                [(cid, name, path, now) for cid, name, path in leaves],
            )
            self._conn.commit()
            log.info(
                "EbayCategoryCache: refreshed %d leaf categories from eBay Taxonomy API.",
                len(leaves),
            )
            return len(leaves)

        except Exception:
            log.warning(
                "EbayCategoryCache: Taxonomy API refresh failed — falling back to bootstrap.",
                exc_info=True,
            )
            self._seed_bootstrap()
            cur = self._conn.execute("SELECT COUNT(*) FROM ebay_categories")
            return cur.fetchone()[0]


def _extract_leaves(
    node: dict,
    path: str,
    leaves: list[tuple[str, str, str]],
) -> None:
    """Recursively walk the eBay category tree, collecting leaf node tuples.

    Args:
        node: A categoryTreeNode dict from the eBay Taxonomy API response.
        path: The ancestor breadcrumb, e.g. "Consumer Electronics > Computers".
        leaves: Accumulator list of (category_id, name, full_path) tuples.
    """
    cat = node["category"]
    cat_id: str = cat["categoryId"]
    cat_name: str = cat["categoryName"]
    full_path = f"{path} > {cat_name}" if path else cat_name

    if node.get("leafCategoryTreeNode", False):
        leaves.append((cat_id, cat_name, full_path))
        return  # leaf — no children to recurse into

    for child in node.get("childCategoryTreeNodes", []):
        _extract_leaves(child, full_path, leaves)
