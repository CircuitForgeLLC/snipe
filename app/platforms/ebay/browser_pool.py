"""Thread-local Playwright browser manager for the eBay scraper.

Each uvicorn worker thread that calls fetch_html() gets its own Playwright
instance, browser, and context — created lazily on first use.  This avoids
the "cannot switch to a different thread" error that arises when Playwright
sync API instances are shared across threads (they bind their greenlet event
loop to the creating thread).

Key design:
- Thread-local: _thread_local.slot holds the _PooledBrowser for the current
  thread.  No slot is ever handed to another thread.
- Lazy creation: slots are created on first fetch_html() call per thread, not
  at startup.  start() is a lightweight lifecycle marker only.
- Registry: _slot_registry (keyed by thread-id) lets stop() close every active
  slot across all threads without walking thread-local storage.
- Replenishment: after each use the dirty context is closed and a fresh one
  opened on the same browser.  Browser launch overhead is paid at most once
  per worker thread lifetime.
- Graceful degradation: if Playwright / Xvfb is unavailable, fetch_html falls
  back to _fetch_fresh (identical behavior to before this module existed).

Pool size is read from BROWSER_POOL_SIZE env var (default: 2) but is now a
soft limit — used only for documentation; actual concurrency is bounded by
uvicorn's thread count.
"""
from __future__ import annotations

import itertools
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

_pool_display_counter = itertools.cycle(range(200, 400))

_CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]
_XVFB_ARGS = ["-screen", "0", "1280x800x24", "-ac"]
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_VIEWPORT = {"width": 1280, "height": 800}

# Thread-local storage: each thread gets its own _PooledBrowser slot.
_thread_local = threading.local()


@dataclass
class _PooledBrowser:
    """One browser slot, bound to a single thread."""
    xvfb: subprocess.Popen
    pw: object          # playwright instance (sync_playwright().__enter__())
    browser: object     # playwright Browser
    ctx: object         # playwright BrowserContext (fresh per use)
    display_num: int
    last_used_ts: float = field(default_factory=time.time)


def _launch_slot() -> _PooledBrowser:
    """Launch a new Xvfb display + headed Chromium browser + fresh context.

    Must be called from the thread that will use the slot.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth  # noqa: F401

    display_num = next(_pool_display_counter)
    display = f":{display_num}"
    env = os.environ.copy()
    env["DISPLAY"] = display

    xvfb = subprocess.Popen(
        ["Xvfb", display] + _XVFB_ARGS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(
            headless=False,
            env=env,
            args=_CHROMIUM_ARGS,
        )
        ctx = browser.new_context(
            user_agent=_USER_AGENT,
            viewport=_VIEWPORT,
        )
    except Exception:
        pw.stop()
        xvfb.terminate()
        xvfb.wait()
        raise

    return _PooledBrowser(
        xvfb=xvfb,
        pw=pw,
        browser=browser,
        ctx=ctx,
        display_num=display_num,
        last_used_ts=time.time(),
    )


def _close_slot(slot: _PooledBrowser) -> None:
    """Cleanly close a slot: context → browser → Playwright → Xvfb."""
    try:
        slot.ctx.close()
    except Exception:
        pass
    try:
        slot.browser.close()
    except Exception:
        pass
    try:
        slot.pw.stop()
    except Exception:
        pass
    try:
        slot.xvfb.terminate()
        slot.xvfb.wait(timeout=5)
    except Exception:
        pass


def _replenish_slot(slot: _PooledBrowser) -> _PooledBrowser:
    """Close the used context and open a fresh one on the same browser."""
    try:
        slot.ctx.close()
    except Exception:
        pass

    new_ctx = slot.browser.new_context(
        user_agent=_USER_AGENT,
        viewport=_VIEWPORT,
    )
    return _PooledBrowser(
        xvfb=slot.xvfb,
        pw=slot.pw,
        browser=slot.browser,
        ctx=new_ctx,
        display_num=slot.display_num,
        last_used_ts=time.time(),
    )


class BrowserPool:
    """Thread-local Playwright browser manager.

    Each thread that calls fetch_html() owns its own browser instance.
    No slots are shared between threads.
    """

    def __init__(self, size: int = 2) -> None:
        self._size = size
        self._lock = threading.Lock()
        self._started = False
        self._stopped = False
        self._playwright_available: Optional[bool] = None
        # Registry of all active slots keyed by thread id — used only by stop().
        self._slot_registry: dict[int, _PooledBrowser] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Mark the pool as started.  Slots are created lazily per thread."""
        with self._lock:
            if self._started:
                return
            self._started = True

        if not self._check_playwright():
            log.warning(
                "BrowserPool: Playwright / Xvfb not available — "
                "pool disabled, falling back to per-call fresh browser."
            )
            return

        log.info("BrowserPool: started (thread-local mode, size hint=%d)", self._size)

    def stop(self) -> None:
        """Close all active slots across all threads."""
        with self._lock:
            self._stopped = True
            registry_snapshot = dict(self._slot_registry)

        closed = 0
        for slot in registry_snapshot.values():
            _close_slot(slot)
            closed += 1
        self._slot_registry.clear()
        log.info("BrowserPool: stopped, closed %d slot(s)", closed)

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def fetch_html(
        self,
        url: str,
        delay: float = 1.0,
        wait_for_selector: Optional[str] = None,
        wait_for_timeout_ms: int = 2000,
    ) -> str:
        """Navigate to *url* and return the rendered HTML.

        Uses the calling thread's browser slot (creates one if needed).
        Falls back to a fresh browser if Playwright is unavailable or the
        slot fails.
        """
        time.sleep(delay)

        slot = self._get_or_create_thread_slot()

        if slot is not None:
            try:
                html = self._fetch_with_slot(
                    slot, url,
                    wait_for_selector=wait_for_selector,
                    wait_for_timeout_ms=wait_for_timeout_ms,
                )
                try:
                    fresh_slot = _replenish_slot(slot)
                    self._register_slot(fresh_slot)
                except Exception as exc:
                    log.warning("BrowserPool: replenish failed, slot discarded: %s", exc)
                    _close_slot(slot)
                    self._unregister_slot()
                return html
            except Exception as exc:
                log.warning("BrowserPool: pooled fetch failed (%s) — closing slot", exc)
                _close_slot(slot)
                self._unregister_slot()

        return self._fetch_fresh(
            url,
            wait_for_selector=wait_for_selector,
            wait_for_timeout_ms=wait_for_timeout_ms,
        )

    # ------------------------------------------------------------------
    # Thread-local slot management
    # ------------------------------------------------------------------

    def _get_or_create_thread_slot(self) -> Optional[_PooledBrowser]:
        """Return the calling thread's slot, creating it if absent."""
        if not self._check_playwright():
            return None

        slot: Optional[_PooledBrowser] = getattr(_thread_local, "slot", None)
        if slot is not None:
            return slot

        try:
            slot = _launch_slot()
            self._register_slot(slot)
            log.debug("BrowserPool: launched slot :%d for thread %d",
                      slot.display_num, threading.get_ident())
            return slot
        except Exception as exc:
            log.warning("BrowserPool: slot launch failed: %s", exc)
            return None

    def _register_slot(self, slot: _PooledBrowser) -> None:
        """Bind slot to the calling thread (both thread-local and registry)."""
        _thread_local.slot = slot
        with self._lock:
            self._slot_registry[threading.get_ident()] = slot

    def _unregister_slot(self) -> None:
        """Remove the calling thread's slot from thread-local and registry."""
        _thread_local.slot = None
        with self._lock:
            self._slot_registry.pop(threading.get_ident(), None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_playwright(self) -> bool:
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            import playwright  # noqa: F401
            from playwright_stealth import Stealth  # noqa: F401
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    def _fetch_with_slot(
        self,
        slot: _PooledBrowser,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_for_timeout_ms: int = 2000,
    ) -> str:
        from playwright_stealth import Stealth

        page = slot.ctx.new_page()
        try:
            Stealth().apply_stealth_sync(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=15_000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(wait_for_timeout_ms)
            return page.content()
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _fetch_fresh(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_for_timeout_ms: int = 2000,
    ) -> str:
        import subprocess as _subprocess

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
        except ImportError as exc:
            raise RuntimeError(
                "Playwright not installed — cannot fetch pages. "
                "Install playwright and playwright-stealth in the Docker image."
            ) from exc

        display_num = next(_pool_display_counter)
        display = f":{display_num}"
        env = os.environ.copy()
        env["DISPLAY"] = display

        xvfb = _subprocess.Popen(
            ["Xvfb", display] + _XVFB_ARGS,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
        )
        time.sleep(0.3)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=False,
                    env=env,
                    args=_CHROMIUM_ARGS,
                )
                ctx = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport=_VIEWPORT,
                )
                page = ctx.new_page()
                Stealth().apply_stealth_sync(page)
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=15_000)
                    except Exception:
                        pass
                else:
                    page.wait_for_timeout(wait_for_timeout_ms)
                html = page.content()
                browser.close()
        finally:
            xvfb.terminate()
            xvfb.wait()

        return html


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_pool() -> BrowserPool:
    """Return the module-level BrowserPool singleton (creates it if needed)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                size = int(os.environ.get("BROWSER_POOL_SIZE", "2"))
                _pool = BrowserPool(size)
    return _pool
