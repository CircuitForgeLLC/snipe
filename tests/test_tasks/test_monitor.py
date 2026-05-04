"""Tests for the background monitor: should_alert logic, store alert methods, and run_monitor_search."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.monitor import _AUCTION_ALERT_WINDOW_HOURS, should_alert


# ---------------------------------------------------------------------------
# should_alert — pure function, no I/O
# ---------------------------------------------------------------------------


class TestShouldAlert:
    def test_bin_above_threshold_alerts(self):
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="fixed_price",
            min_trust_score=60,
        ) is True

    def test_bin_below_threshold_no_alert(self):
        assert should_alert(
            trust_score=55, score_is_partial=False,
            price=100.0, buying_format="fixed_price",
            min_trust_score=60,
        ) is False

    def test_partial_score_applies_buffer(self):
        # Score 65 with min 60 passes normally but fails with the +10 partial buffer.
        assert should_alert(
            trust_score=65, score_is_partial=True,
            price=100.0, buying_format="fixed_price",
            min_trust_score=60,
        ) is False

    def test_partial_score_above_buffered_threshold_alerts(self):
        assert should_alert(
            trust_score=75, score_is_partial=True,
            price=100.0, buying_format="fixed_price",
            min_trust_score=60,
        ) is True

    def test_best_offer_treated_like_bin(self):
        assert should_alert(
            trust_score=80, score_is_partial=False,
            price=200.0, buying_format="best_offer",
            min_trust_score=60,
        ) is True

    def test_auction_within_window_alerts(self):
        soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at=soon,
        ) is True

    def test_auction_outside_window_no_alert(self):
        far = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at=far,
        ) is False

    def test_auction_no_ends_at_alerts_anyway(self):
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at=None,
        ) is True

    def test_auction_bad_ends_at_alerts_anyway(self):
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at="not-a-date",
        ) is True

    def test_auction_expired_no_alert(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at=past,
        ) is False

    def test_unknown_format_alerts(self):
        # Fail-open: unknown buying_format should not silently suppress.
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="mystery_format",
            min_trust_score=60,
        ) is True

    def test_score_exactly_at_threshold_passes(self):
        assert should_alert(
            trust_score=60, score_is_partial=False,
            price=100.0, buying_format="fixed_price",
            min_trust_score=60,
        ) is True

    def test_auction_exactly_at_window_boundary_alerts(self):
        boundary = (datetime.now(timezone.utc) + timedelta(hours=_AUCTION_ALERT_WINDOW_HOURS - 0.1)).isoformat()
        assert should_alert(
            trust_score=70, score_is_partial=False,
            price=100.0, buying_format="auction",
            min_trust_score=60, ends_at=boundary,
        ) is True


# ---------------------------------------------------------------------------
# Store alert methods — integration against real SQLite
# ---------------------------------------------------------------------------


def _create_monitor_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            query TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'ebay',
            filters_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_run_at TEXT,
            monitor_enabled INTEGER NOT NULL DEFAULT 0,
            poll_interval_min INTEGER NOT NULL DEFAULT 60,
            min_trust_score INTEGER NOT NULL DEFAULT 60,
            last_checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS watch_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_search_id INTEGER NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
            platform_listing_id TEXT NOT NULL,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            trust_score INTEGER NOT NULL,
            url TEXT,
            first_alerted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dismissed_at TEXT,
            UNIQUE(saved_search_id, platform_listing_id)
        );
        INSERT INTO saved_searches (name, query, monitor_enabled) VALUES ('RTX 4090', 'rtx 4090', 1);
    """)
    conn.commit()
    conn.close()


@pytest.fixture
def monitor_db(tmp_path: Path) -> Path:
    db = tmp_path / "snipe.db"
    _create_monitor_db(db)
    return db


class TestStoreAlertMethods:
    def test_upsert_alert_new(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        alert = WatchAlert(
            saved_search_id=1, platform_listing_id="ebay-001",
            title="RTX 4090", price=750.0, trust_score=72, currency="USD",
            url="https://ebay.com/itm/001",
        )
        alert_id, is_new = store.upsert_alert(alert)
        assert is_new is True
        assert alert_id > 0

    def test_upsert_alert_dedup(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        alert = WatchAlert(
            saved_search_id=1, platform_listing_id="ebay-002",
            title="RTX 4090 FE", price=800.0, trust_score=68,
        )
        id1, new1 = store.upsert_alert(alert)
        id2, new2 = store.upsert_alert(alert)
        assert id1 == id2
        assert new1 is True
        assert new2 is False

    def test_list_alerts_returns_undismissed(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        alert = WatchAlert(
            saved_search_id=1, platform_listing_id="ebay-003",
            title="Test listing", price=500.0, trust_score=75,
        )
        store.upsert_alert(alert)
        alerts = store.list_alerts(include_dismissed=False)
        assert len(alerts) == 1
        assert alerts[0].platform_listing_id == "ebay-003"

    def test_count_undismissed_alerts(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        for i in range(3):
            store.upsert_alert(WatchAlert(
                saved_search_id=1, platform_listing_id=f"ebay-{i:03d}",
                title=f"Listing {i}", price=float(100 + i), trust_score=70,
            ))
        assert store.count_undismissed_alerts() == 3

    def test_dismiss_alert(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        alert = WatchAlert(
            saved_search_id=1, platform_listing_id="ebay-dismiss",
            title="To dismiss", price=400.0, trust_score=65,
        )
        alert_id, _ = store.upsert_alert(alert)
        store.dismiss_alert(alert_id)
        alerts = store.list_alerts(include_dismissed=False)
        assert all(a.id != alert_id for a in alerts)

    def test_dismiss_all_alerts(self, monitor_db: Path):
        from app.db.models import WatchAlert
        from app.db.store import Store

        store = Store(monitor_db)
        for i in range(3):
            store.upsert_alert(WatchAlert(
                saved_search_id=1, platform_listing_id=f"all-{i}",
                title=f"All {i}", price=float(100 * i), trust_score=70,
            ))
        count = store.dismiss_all_alerts()
        assert count == 3
        assert store.count_undismissed_alerts() == 0

    def test_mark_search_checked_updates_timestamp(self, monitor_db: Path):
        from app.db.store import Store

        store = Store(monitor_db)
        store.mark_search_checked(1)
        searches = store.list_monitored_searches()
        assert searches[0].last_checked_at is not None


# ---------------------------------------------------------------------------
# run_monitor_search — mocked adapter + trust aggregator
# ---------------------------------------------------------------------------


class TestRunMonitorSearch:
    def test_new_qualifying_listing_creates_alert(self, monitor_db: Path):
        from app.db.models import Listing, SavedSearch, TrustScore
        from app.db.store import Store
        from app.tasks.monitor import run_monitor_search

        search = SavedSearch(
            id=1, name="RTX 4090", query="rtx 4090",
            platform="ebay", monitor_enabled=True,
            min_trust_score=60,
        )
        mock_listing = Listing(
            platform="ebay", platform_listing_id="ebay-new",
            title="ASUS RTX 4090", price=750.0, currency="USD",
            condition="used", url="https://ebay.com/itm/new",
            buying_format="fixed_price", seller_platform_id="seller123",
        )
        mock_trust = TrustScore(
            listing_id=0, composite_score=72, score_is_partial=False,
            account_age_score=0, feedback_count_score=0, feedback_ratio_score=0,
            price_vs_market_score=0, category_history_score=0,
        )

        with patch("app.platforms.ebay.adapter.EbayAdapter") as MockAdapter, \
             patch("app.trust.TrustScorer") as MockAgg:
            MockAdapter.return_value.search.return_value = [mock_listing]
            MockAgg.return_value.score_batch.return_value = [mock_trust]

            count = run_monitor_search(search, user_db=monitor_db, shared_db=monitor_db)

        assert count == 1
        alerts = Store(monitor_db).list_alerts()
        assert len(alerts) == 1
        assert alerts[0].platform_listing_id == "ebay-new"

    def test_below_threshold_listing_not_alerted(self, monitor_db: Path):
        from app.db.models import Listing, SavedSearch, TrustScore
        from app.tasks.monitor import run_monitor_search

        search = SavedSearch(
            id=1, name="RTX 4090", query="rtx 4090",
            platform="ebay", monitor_enabled=True,
            min_trust_score=70,
        )
        mock_listing = Listing(
            platform="ebay", platform_listing_id="ebay-low",
            title="Sketchy RTX 4090", price=500.0, currency="USD",
            condition="used", url="https://ebay.com/itm/low",
            buying_format="fixed_price", seller_platform_id="s1",
        )
        mock_trust = TrustScore(
            listing_id=0, composite_score=55, score_is_partial=False,
            account_age_score=0, feedback_count_score=0, feedback_ratio_score=0,
            price_vs_market_score=0, category_history_score=0,
        )

        with patch("app.platforms.ebay.adapter.EbayAdapter") as MockAdapter, \
             patch("app.trust.TrustScorer") as MockAgg:
            MockAdapter.return_value.search.return_value = [mock_listing]
            MockAgg.return_value.score_batch.return_value = [mock_trust]

            count = run_monitor_search(search, user_db=monitor_db, shared_db=monitor_db)

        assert count == 0

    def test_duplicate_listing_not_double_alerted(self, monitor_db: Path):
        from app.db.models import Listing, SavedSearch, TrustScore
        from app.tasks.monitor import run_monitor_search

        search = SavedSearch(
            id=1, name="RTX 4090", query="rtx 4090",
            platform="ebay", monitor_enabled=True, min_trust_score=60,
        )
        mock_listing = Listing(
            platform="ebay", platform_listing_id="ebay-dupe",
            title="RTX 4090", price=700.0, currency="USD",
            condition="used", url="https://ebay.com/itm/dupe",
            buying_format="fixed_price", seller_platform_id="s1",
        )
        mock_trust = TrustScore(
            listing_id=0, composite_score=75, score_is_partial=False,
            account_age_score=0, feedback_count_score=0, feedback_ratio_score=0,
            price_vs_market_score=0, category_history_score=0,
        )

        with patch("app.platforms.ebay.adapter.EbayAdapter") as MockAdapter, \
             patch("app.trust.TrustScorer") as MockAgg:
            MockAdapter.return_value.search.return_value = [mock_listing]
            MockAgg.return_value.score_batch.return_value = [mock_trust]

            count1 = run_monitor_search(search, user_db=monitor_db, shared_db=monitor_db)
            count2 = run_monitor_search(search, user_db=monitor_db, shared_db=monitor_db)

        assert count1 == 1
        assert count2 == 0  # deduped by UNIQUE constraint

    def test_adapter_failure_returns_zero(self, monitor_db: Path):
        from app.db.models import SavedSearch
        from app.tasks.monitor import run_monitor_search

        search = SavedSearch(
            id=1, name="RTX 4090", query="rtx 4090",
            platform="ebay", monitor_enabled=True, min_trust_score=60,
        )

        with patch("app.platforms.ebay.adapter.EbayAdapter") as MockAdapter:
            MockAdapter.return_value.search.side_effect = RuntimeError("eBay down")
            count = run_monitor_search(search, user_db=monitor_db, shared_db=monitor_db)

        assert count == 0
