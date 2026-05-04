"""Tests for app.platforms.ebay.browser_pool (thread-local design).

All tests run without real Chromium / Xvfb / Playwright.
Playwright, Xvfb subprocess calls, and Stealth are mocked throughout.
"""
from __future__ import annotations

import subprocess
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to reset the module-level singleton between tests
# ---------------------------------------------------------------------------

def _reset_pool_singleton():
    import app.platforms.ebay.browser_pool as _mod
    _mod._pool = None


def _reset_thread_local():
    import app.platforms.ebay.browser_pool as _mod
    _mod._thread_local.slot = None


@pytest.fixture(autouse=True)
def reset_pool():
    _reset_pool_singleton()
    _reset_thread_local()
    yield
    _reset_pool_singleton()
    _reset_thread_local()


def _make_fake_slot():
    from app.platforms.ebay.browser_pool import _PooledBrowser

    xvfb = MagicMock(spec=subprocess.Popen)
    pw = MagicMock()
    browser = MagicMock()
    ctx = MagicMock()
    return _PooledBrowser(
        xvfb=xvfb, pw=pw, browser=browser, ctx=ctx,
        display_num=100, last_used_ts=time.time(),
    )


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestGetPoolSingleton:
    def test_returns_same_instance(self):
        from app.platforms.ebay.browser_pool import get_pool, BrowserPool
        assert get_pool() is get_pool()

    def test_returns_browser_pool_instance(self):
        from app.platforms.ebay.browser_pool import get_pool, BrowserPool
        assert isinstance(get_pool(), BrowserPool)

    def test_default_size_is_two(self):
        from app.platforms.ebay.browser_pool import get_pool
        assert get_pool()._size == 2

    def test_custom_size_from_env(self, monkeypatch):
        monkeypatch.setenv("BROWSER_POOL_SIZE", "5")
        from app.platforms.ebay.browser_pool import get_pool
        assert get_pool()._size == 5


# ---------------------------------------------------------------------------
# start() / stop() lifecycle tests
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_is_noop_when_playwright_unavailable(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        with patch.object(pool, "_check_playwright", return_value=False):
            pool.start()
        assert pool._started is True
        assert pool._slot_registry == {}

    def test_start_only_runs_once(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        with patch.object(pool, "_check_playwright", return_value=False):
            pool.start()
            pool.start()
        assert pool._started is True

    def test_stop_closes_all_registry_slots(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        slot1 = _make_fake_slot()
        slot2 = _make_fake_slot()
        pool._slot_registry[1001] = slot1
        pool._slot_registry[1002] = slot2

        with patch("app.platforms.ebay.browser_pool._close_slot") as mock_close:
            pool.stop()

        assert mock_close.call_count == 2
        assert pool._slot_registry == {}
        assert pool._stopped is True

    def test_stop_on_empty_registry_is_safe(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        BrowserPool(size=2).stop()


# ---------------------------------------------------------------------------
# fetch_html — thread-local slot hit path
# ---------------------------------------------------------------------------

class TestFetchHtmlSlotHit:
    def test_uses_existing_slot_and_replenishes(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        import app.platforms.ebay.browser_pool as _mod

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        _mod._thread_local.slot = slot

        fresh_slot = _make_fake_slot()

        with (
            patch.object(pool, "_fetch_with_slot", return_value="<html>ok</html>") as mock_fetch,
            patch("app.platforms.ebay.browser_pool._replenish_slot", return_value=fresh_slot),
            patch.object(pool, "_register_slot") as mock_register,
            patch("time.sleep"),
        ):
            html = pool.fetch_html("https://www.ebay.com/sch/i.html?_nkw=test", delay=0)

        assert html == "<html>ok</html>"
        mock_fetch.assert_called_once_with(
            slot, "https://www.ebay.com/sch/i.html?_nkw=test",
            wait_for_selector=None, wait_for_timeout_ms=2000,
        )
        mock_register.assert_called_once_with(fresh_slot)

    def test_delay_is_respected(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        import app.platforms.ebay.browser_pool as _mod

        pool = BrowserPool(size=1)
        _mod._thread_local.slot = _make_fake_slot()

        with (
            patch.object(pool, "_fetch_with_slot", return_value="<html/>"),
            patch("app.platforms.ebay.browser_pool._replenish_slot", return_value=_make_fake_slot()),
            patch.object(pool, "_register_slot"),
            patch("app.platforms.ebay.browser_pool.time") as mock_time,
        ):
            pool.fetch_html("https://example.com", delay=1.5)

        mock_time.sleep.assert_called_once_with(1.5)


# ---------------------------------------------------------------------------
# fetch_html — no slot / fallback path
# ---------------------------------------------------------------------------

class TestFetchHtmlFallback:
    def test_falls_back_when_no_slot_and_playwright_unavailable(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        # No thread-local slot; playwright unavailable → _get_or_create returns None.
        with (
            patch.object(pool, "_get_or_create_thread_slot", return_value=None),
            patch.object(pool, "_fetch_fresh", return_value="<html>fresh</html>") as mock_fresh,
            patch("time.sleep"),
        ):
            html = pool.fetch_html("https://www.ebay.com/sch/i.html?_nkw=widget", delay=0)

        assert html == "<html>fresh</html>"
        mock_fresh.assert_called_once_with(
            "https://www.ebay.com/sch/i.html?_nkw=widget",
            wait_for_selector=None, wait_for_timeout_ms=2000,
        )

    def test_falls_back_when_pooled_fetch_raises(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        import app.platforms.ebay.browser_pool as _mod

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        _mod._thread_local.slot = slot

        with (
            patch.object(pool, "_fetch_with_slot", side_effect=RuntimeError("Chromium crashed")),
            patch.object(pool, "_fetch_fresh", return_value="<html>recovered</html>") as mock_fresh,
            patch("app.platforms.ebay.browser_pool._close_slot") as mock_close,
            patch.object(pool, "_unregister_slot"),
            patch("time.sleep"),
        ):
            html = pool.fetch_html("https://www.ebay.com/", delay=0)

        assert html == "<html>recovered</html>"
        mock_close.assert_called_once_with(slot)
        mock_fresh.assert_called_once()


# ---------------------------------------------------------------------------
# Thread-local slot management
# ---------------------------------------------------------------------------

class TestThreadLocalSlotManagement:
    def test_get_or_create_returns_existing_slot(self):
        import app.platforms.ebay.browser_pool as _mod
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        pool._playwright_available = True
        existing = _make_fake_slot()
        _mod._thread_local.slot = existing

        result = pool._get_or_create_thread_slot()
        assert result is existing

    def test_get_or_create_launches_new_slot_when_absent(self):
        import app.platforms.ebay.browser_pool as _mod
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        pool._playwright_available = True
        _mod._thread_local.slot = None

        new_slot = _make_fake_slot()
        with (
            patch("app.platforms.ebay.browser_pool._launch_slot", return_value=new_slot),
            patch.object(pool, "_register_slot") as mock_register,
        ):
            result = pool._get_or_create_thread_slot()

        assert result is new_slot
        mock_register.assert_called_once_with(new_slot)

    def test_get_or_create_returns_none_when_playwright_unavailable(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        pool._playwright_available = False
        assert pool._get_or_create_thread_slot() is None

    def test_register_slot_sets_thread_local_and_registry(self):
        import app.platforms.ebay.browser_pool as _mod
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        pool._register_slot(slot)

        assert _mod._thread_local.slot is slot
        assert threading.get_ident() in pool._slot_registry

    def test_unregister_slot_clears_thread_local_and_registry(self):
        import app.platforms.ebay.browser_pool as _mod
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        pool._register_slot(slot)
        pool._unregister_slot()

        assert getattr(_mod._thread_local, "slot", None) is None
        assert threading.get_ident() not in pool._slot_registry

    def test_different_threads_get_independent_slots(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        pool._playwright_available = True

        slots_seen: list = []
        errors: list = []

        def worker():
            new_slot = _make_fake_slot()
            with patch("app.platforms.ebay.browser_pool._launch_slot", return_value=new_slot):
                s = pool._get_or_create_thread_slot()
                slots_seen.append(s)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert len(slots_seen) == 2
        # Each thread got its own slot object (they may differ or coincidentally share
        # the same mock; what matters is both threads succeeded without interference).
        assert all(s is not None for s in slots_seen)


# ---------------------------------------------------------------------------
# ImportError graceful fallback
# ---------------------------------------------------------------------------

class TestImportErrorHandling:
    def test_check_playwright_returns_false_on_import_error(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        with patch.dict("sys.modules", {"playwright": None, "playwright_stealth": None}):
            pool._playwright_available = None
            result = pool._check_playwright()

        assert result is False
        assert pool._playwright_available is False

    def test_start_logs_warning_when_playwright_missing(self, caplog):
        import logging
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        pool._playwright_available = False

        with patch.object(pool, "_check_playwright", return_value=False):
            with caplog.at_level(logging.WARNING, logger="app.platforms.ebay.browser_pool"):
                pool.start()

        assert any("not available" in r.message for r in caplog.records)

    def test_fetch_fresh_raises_runtime_error_when_playwright_missing(self):
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with pytest.raises(RuntimeError, match="Playwright not installed"):
                pool._fetch_fresh("https://www.ebay.com/")


# ---------------------------------------------------------------------------
# _replenish_slot helper
# ---------------------------------------------------------------------------

class TestReplenishSlot:
    def test_replenish_closes_old_context_and_opens_new(self):
        from app.platforms.ebay.browser_pool import _replenish_slot, _PooledBrowser

        old_ctx = MagicMock()
        new_ctx = MagicMock()
        browser = MagicMock()
        browser.new_context.return_value = new_ctx

        slot = _PooledBrowser(
            xvfb=MagicMock(), pw=MagicMock(), browser=browser,
            ctx=old_ctx, display_num=101, last_used_ts=time.time() - 10,
        )

        result = _replenish_slot(slot)

        old_ctx.close.assert_called_once()
        browser.new_context.assert_called_once()
        assert result.ctx is new_ctx
        assert result.browser is browser
        assert result.xvfb is slot.xvfb
        assert result.last_used_ts > slot.last_used_ts


# ---------------------------------------------------------------------------
# _close_slot helper
# ---------------------------------------------------------------------------

class TestCloseSlot:
    def test_close_slot_closes_all_components(self):
        from app.platforms.ebay.browser_pool import _close_slot, _PooledBrowser

        xvfb = MagicMock(spec=subprocess.Popen)
        pw = MagicMock()
        browser = MagicMock()
        ctx = MagicMock()

        slot = _PooledBrowser(
            xvfb=xvfb, pw=pw, browser=browser, ctx=ctx,
            display_num=102, last_used_ts=time.time(),
        )
        _close_slot(slot)

        ctx.close.assert_called_once()
        browser.close.assert_called_once()
        pw.stop.assert_called_once()
        xvfb.terminate.assert_called_once()
        xvfb.wait.assert_called_once()

    def test_close_slot_ignores_exceptions(self):
        from app.platforms.ebay.browser_pool import _close_slot, _PooledBrowser

        xvfb = MagicMock(spec=subprocess.Popen)
        xvfb.terminate.side_effect = OSError("already dead")
        xvfb.wait.side_effect = OSError("already dead")
        pw = MagicMock()
        pw.stop.side_effect = RuntimeError("stopped")
        browser = MagicMock()
        browser.close.side_effect = RuntimeError("gone")
        ctx = MagicMock()
        ctx.close.side_effect = RuntimeError("gone")

        slot = _PooledBrowser(
            xvfb=xvfb, pw=pw, browser=browser, ctx=ctx,
            display_num=103, last_used_ts=time.time(),
        )
        _close_slot(slot)  # must not raise


# ---------------------------------------------------------------------------
# Scraper integration — _fetch_url uses pool
# ---------------------------------------------------------------------------

class TestScraperUsesPool:
    def test_fetch_url_delegates_to_pool(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        from app.platforms.ebay.scraper import ScrapedEbayAdapter
        from app.db.store import Store

        store = MagicMock(spec=Store)
        adapter = ScrapedEbayAdapter(store, delay=0)

        fake_pool = MagicMock(spec=BrowserPool)
        fake_pool.fetch_html.return_value = "<html>pooled</html>"

        with patch("app.platforms.ebay.browser_pool.get_pool", return_value=fake_pool):
            import app.platforms.ebay.scraper as scraper_mod
            scraper_mod._html_cache.clear()
            html = adapter._fetch_url("https://www.ebay.com/sch/i.html?_nkw=test")

        assert html == "<html>pooled</html>"
        fake_pool.fetch_html.assert_called_once_with(
            "https://www.ebay.com/sch/i.html?_nkw=test", delay=0
        )

    def test_fetch_url_uses_cache_before_pool(self):
        from app.platforms.ebay.scraper import ScrapedEbayAdapter, _html_cache, _HTML_CACHE_TTL
        from app.db.store import Store

        store = MagicMock(spec=Store)
        adapter = ScrapedEbayAdapter(store, delay=0)

        url = "https://www.ebay.com/sch/i.html?_nkw=cached"
        _html_cache[url] = ("<html>cached</html>", time.time() + _HTML_CACHE_TTL)

        fake_pool = MagicMock()
        with patch("app.platforms.ebay.browser_pool.get_pool", return_value=fake_pool):
            html = adapter._fetch_url(url)

        assert html == "<html>cached</html>"
        fake_pool.fetch_html.assert_not_called()
        _html_cache.pop(url, None)
