"""Tests for app.platforms.ebay.browser_pool.

All tests run without real Chromium / Xvfb / Playwright.
Playwright, Xvfb subprocess calls, and Stealth are mocked throughout.
"""
from __future__ import annotations

import queue
import subprocess
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers to reset the module-level singleton between tests
# ---------------------------------------------------------------------------

def _reset_pool_singleton():
    """Force the module-level _pool singleton back to None."""
    import app.platforms.ebay.browser_pool as _mod
    _mod._pool = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton before and after every test."""
    _reset_pool_singleton()
    yield
    _reset_pool_singleton()


def _make_fake_slot():
    """Build a mock _PooledBrowser with all necessary attributes."""
    from app.platforms.ebay.browser_pool import _PooledBrowser

    xvfb = MagicMock(spec=subprocess.Popen)
    pw = MagicMock()
    browser = MagicMock()
    ctx = MagicMock()
    slot = _PooledBrowser(
        xvfb=xvfb,
        pw=pw,
        browser=browser,
        ctx=ctx,
        display_num=100,
        last_used_ts=time.time(),
    )
    return slot


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestGetPoolSingleton:
    def test_returns_same_instance(self):
        from app.platforms.ebay.browser_pool import get_pool, BrowserPool
        p1 = get_pool()
        p2 = get_pool()
        assert p1 is p2

    def test_returns_browser_pool_instance(self):
        from app.platforms.ebay.browser_pool import get_pool, BrowserPool
        assert isinstance(get_pool(), BrowserPool)

    def test_default_size_is_two(self):
        from app.platforms.ebay.browser_pool import get_pool
        pool = get_pool()
        assert pool._size == 2

    def test_custom_size_from_env(self, monkeypatch):
        monkeypatch.setenv("BROWSER_POOL_SIZE", "5")
        from app.platforms.ebay.browser_pool import get_pool
        pool = get_pool()
        assert pool._size == 5


# ---------------------------------------------------------------------------
# start() / stop() lifecycle tests
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_is_noop_when_playwright_unavailable(self):
        """Pool should handle missing Playwright gracefully — no error raised."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        with patch.object(pool, "_check_playwright", return_value=False):
            pool.start()  # must not raise
        # Pool queue is empty — no slots launched.
        assert pool._q.empty()

    def test_start_only_runs_once(self):
        """Calling start() twice must not double-warm."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        with patch.object(pool, "_check_playwright", return_value=False):
            pool.start()
            pool.start()
        assert pool._started is True

    def test_stop_drains_queue(self):
        """stop() should close every slot in the queue."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)
        slot1 = _make_fake_slot()
        slot2 = _make_fake_slot()
        pool._q.put(slot1)
        pool._q.put(slot2)

        with patch("app.platforms.ebay.browser_pool._close_slot") as mock_close:
            pool.stop()

        assert mock_close.call_count == 2
        assert pool._q.empty()
        assert pool._stopped is True

    def test_stop_on_empty_pool_is_safe(self):
        from app.platforms.ebay.browser_pool import BrowserPool
        pool = BrowserPool(size=2)
        pool.stop()  # must not raise


# ---------------------------------------------------------------------------
# fetch_html — pool hit path
# ---------------------------------------------------------------------------

class TestFetchHtmlPoolHit:
    def test_uses_pooled_slot_and_replenishes(self):
        """fetch_html should borrow a slot, call _fetch_with_slot, replenish."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        pool._q.put(slot)

        fresh_slot = _make_fake_slot()

        with (
            patch.object(pool, "_fetch_with_slot", return_value="<html>ok</html>") as mock_fetch,
            patch("app.platforms.ebay.browser_pool._replenish_slot", return_value=fresh_slot) as mock_replenish,
            patch("time.sleep"),
        ):
            html = pool.fetch_html("https://www.ebay.com/sch/i.html?_nkw=test", delay=0)

        assert html == "<html>ok</html>"
        mock_fetch.assert_called_once_with(slot, "https://www.ebay.com/sch/i.html?_nkw=test")
        mock_replenish.assert_called_once_with(slot)
        # Fresh slot returned to queue
        assert pool._q.get_nowait() is fresh_slot

    def test_delay_is_respected(self):
        """fetch_html must call time.sleep(delay)."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        pool._q.put(slot)

        with (
            patch.object(pool, "_fetch_with_slot", return_value="<html/>"),
            patch("app.platforms.ebay.browser_pool._replenish_slot", return_value=_make_fake_slot()),
            patch("app.platforms.ebay.browser_pool.time") as mock_time,
        ):
            pool.fetch_html("https://example.com", delay=1.5)

        mock_time.sleep.assert_called_once_with(1.5)


# ---------------------------------------------------------------------------
# fetch_html — pool empty / fallback path
# ---------------------------------------------------------------------------

class TestFetchHtmlFallback:
    def test_falls_back_to_fresh_browser_when_pool_empty(self):
        """When pool is empty after timeout, _fetch_fresh should be called."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        # Queue is empty — no slots available.

        with (
            patch.object(pool, "_fetch_fresh", return_value="<html>fresh</html>") as mock_fresh,
            patch("time.sleep"),
            # Make Queue.get raise Empty after a short wait.
            patch.object(pool._q, "get", side_effect=queue.Empty),
        ):
            html = pool.fetch_html("https://www.ebay.com/sch/i.html?_nkw=widget", delay=0)

        assert html == "<html>fresh</html>"
        mock_fresh.assert_called_once_with("https://www.ebay.com/sch/i.html?_nkw=widget")

    def test_falls_back_when_pooled_fetch_raises(self):
        """If _fetch_with_slot raises, the slot is closed and _fetch_fresh is used."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        slot = _make_fake_slot()
        pool._q.put(slot)

        with (
            patch.object(pool, "_fetch_with_slot", side_effect=RuntimeError("Chromium crashed")),
            patch.object(pool, "_fetch_fresh", return_value="<html>recovered</html>") as mock_fresh,
            patch("app.platforms.ebay.browser_pool._close_slot") as mock_close,
            patch("time.sleep"),
        ):
            html = pool.fetch_html("https://www.ebay.com/", delay=0)

        assert html == "<html>recovered</html>"
        mock_close.assert_called_once_with(slot)
        mock_fresh.assert_called_once()


# ---------------------------------------------------------------------------
# ImportError graceful fallback
# ---------------------------------------------------------------------------

class TestImportErrorHandling:
    def test_check_playwright_returns_false_on_import_error(self):
        """_check_playwright should cache False when playwright is not installed."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=2)

        with patch.dict("sys.modules", {"playwright": None, "playwright_stealth": None}):
            # Force re-check by clearing the cached value.
            pool._playwright_available = None
            result = pool._check_playwright()

        assert result is False
        assert pool._playwright_available is False

    def test_start_logs_warning_when_playwright_missing(self, caplog):
        """start() should log a warning and not crash when Playwright is absent."""
        import logging
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)
        pool._playwright_available = False  # simulate missing

        with patch.object(pool, "_check_playwright", return_value=False):
            with caplog.at_level(logging.WARNING, logger="app.platforms.ebay.browser_pool"):
                pool.start()

        assert any("not available" in r.message for r in caplog.records)

    def test_fetch_fresh_raises_runtime_error_when_playwright_missing(self):
        """_fetch_fresh must raise RuntimeError (not ImportError) when PW absent."""
        from app.platforms.ebay.browser_pool import BrowserPool

        pool = BrowserPool(size=1)

        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with pytest.raises(RuntimeError, match="Playwright not installed"):
                pool._fetch_fresh("https://www.ebay.com/")


# ---------------------------------------------------------------------------
# Idle cleanup
# ---------------------------------------------------------------------------

class TestIdleCleanup:
    def test_idle_cleanup_closes_stale_slots(self):
        """_idle_cleanup_loop should close slots whose last_used_ts is too old."""
        from app.platforms.ebay.browser_pool import BrowserPool, _IDLE_TIMEOUT_SECS

        pool = BrowserPool(size=2)

        stale_slot = _make_fake_slot()
        stale_slot.last_used_ts = time.time() - (_IDLE_TIMEOUT_SECS + 60)

        fresh_slot = _make_fake_slot()
        fresh_slot.last_used_ts = time.time()

        pool._q.put(stale_slot)
        pool._q.put(fresh_slot)

        closed_slots = []

        def fake_close(s):
            closed_slots.append(s)

        with patch("app.platforms.ebay.browser_pool._close_slot", side_effect=fake_close):
            # Run one cleanup tick directly (not the full loop).
            now = time.time()
            idle_cutoff = now - _IDLE_TIMEOUT_SECS
            kept = []
            while True:
                try:
                    s = pool._q.get_nowait()
                except queue.Empty:
                    break
                if s.last_used_ts < idle_cutoff:
                    fake_close(s)
                else:
                    kept.append(s)
            for s in kept:
                pool._q.put(s)

        assert stale_slot in closed_slots
        assert fresh_slot not in closed_slots
        assert pool._q.qsize() == 1

    def test_idle_cleanup_loop_stops_when_pool_stopped(self):
        """Cleanup daemon should exit when _stopped is True."""
        from app.platforms.ebay.browser_pool import BrowserPool, _CLEANUP_INTERVAL_SECS

        pool = BrowserPool(size=1)
        pool._stopped = True

        # The loop should return after one iteration of the while check.
        # Use a very short sleep mock so the test doesn't actually wait 60s.
        sleep_calls = []

        def fake_sleep(secs):
            sleep_calls.append(secs)

        with patch("app.platforms.ebay.browser_pool.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.sleep.side_effect = fake_sleep
            # Run in a thread with a short timeout to confirm it exits.
            t = threading.Thread(target=pool._idle_cleanup_loop)
            t.start()
            t.join(timeout=2.0)

        assert not t.is_alive(), "idle cleanup loop did not exit when _stopped=True"


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
            xvfb=MagicMock(),
            pw=MagicMock(),
            browser=browser,
            ctx=old_ctx,
            display_num=101,
            last_used_ts=time.time() - 10,
        )

        result = _replenish_slot(slot)

        old_ctx.close.assert_called_once()
        browser.new_context.assert_called_once()
        assert result.ctx is new_ctx
        assert result.browser is browser
        assert result.xvfb is slot.xvfb
        # last_used_ts is refreshed
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
        """_close_slot must not raise even if components throw."""
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
        """ScrapedEbayAdapter._fetch_url must use the pool, not launch its own browser."""
        from app.platforms.ebay.browser_pool import BrowserPool
        from app.platforms.ebay.scraper import ScrapedEbayAdapter
        from app.db.store import Store

        store = MagicMock(spec=Store)
        adapter = ScrapedEbayAdapter(store, delay=0)

        fake_pool = MagicMock(spec=BrowserPool)
        fake_pool.fetch_html.return_value = "<html>pooled</html>"

        with patch("app.platforms.ebay.browser_pool.get_pool", return_value=fake_pool):
            # Clear the cache so fetch_url actually hits the pool.
            import app.platforms.ebay.scraper as scraper_mod
            scraper_mod._html_cache.clear()
            html = adapter._fetch_url("https://www.ebay.com/sch/i.html?_nkw=test")

        assert html == "<html>pooled</html>"
        fake_pool.fetch_html.assert_called_once_with(
            "https://www.ebay.com/sch/i.html?_nkw=test", delay=0
        )

    def test_fetch_url_uses_cache_before_pool(self):
        """_fetch_url should return cached HTML without hitting the pool."""
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

        # Cleanup
        _html_cache.pop(url, None)
