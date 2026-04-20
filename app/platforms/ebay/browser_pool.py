"""Pre-warmed Chromium browser pool for the eBay scraper.

Eliminates cold-start latency (5-10s per call) by keeping a small pool of
long-lived Playwright browser instances with fresh contexts ready to serve.

Key design:
- Pool slots: ``(xvfb_proc, pw_instance, browser, context, display_num, last_used_ts)``
  One headed Chromium browser per slot — keeps the Kasada fingerprint clean.
- Thread safety: ``queue.Queue`` with blocking get (timeout=3s before fresh fallback).
- Replenishment: after each use, the dirty context is closed and a new context is
  opened on the *same* browser, then returned to the queue.  Browser launch overhead
  is only paid at startup and during idle-cleanup replenishment.
- Idle cleanup: daemon thread closes slots idle for >5 minutes to avoid memory leaks
  when the service is quiet.
- Graceful degradation: if Playwright / Xvfb is unavailable (host-side test env),
  ``fetch_html`` falls back to launching a fresh browser per call — same behavior
  as before this module existed.

Pool size is controlled via ``BROWSER_POOL_SIZE`` env var (default: 2).
"""
from __future__ import annotations

import itertools
import logging
import os
import queue
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# Reuse the same display counter namespace as scraper.py to avoid collisions.
# Pool uses :100-:199; scraper.py fallback uses :200-:299.
_pool_display_counter = itertools.cycle(range(100, 200))

_IDLE_TIMEOUT_SECS = 300  # 5 minutes
_CLEANUP_INTERVAL_SECS = 60
_QUEUE_TIMEOUT_SECS = 3.0

_CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_VIEWPORT = {"width": 1280, "height": 800}


@dataclass
class _PooledBrowser:
    """One slot in the browser pool."""
    xvfb: subprocess.Popen
    pw: object          # playwright instance (sync_playwright().__enter__())
    browser: object     # playwright Browser
    ctx: object         # playwright BrowserContext (fresh per use)
    display_num: int
    last_used_ts: float = field(default_factory=time.time)


def _launch_slot() -> "_PooledBrowser":
    """Launch a new Xvfb display + headed Chromium browser + fresh context.

    Raises on failure — callers must catch and handle gracefully.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth  # noqa: F401 — imported here to confirm availability

    display_num = next(_pool_display_counter)
    display = f":{display_num}"
    env = os.environ.copy()
    env["DISPLAY"] = display

    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Small grace period for Xvfb to bind the display socket.
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
    """Cleanly close a pool slot: context → browser → Playwright → Xvfb."""
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
    """Close the used context and open a fresh one on the same browser.

    Returns a new _PooledBrowser sharing the same xvfb/pw/browser but with a
    clean context — avoids paying browser launch overhead on every fetch.
    """
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
    """Thread-safe pool of pre-warmed Playwright browser contexts."""

    def __init__(self, size: int = 2) -> None:
        self._size = size
        self._q: queue.Queue[_PooledBrowser] = queue.Queue()
        self._lock = threading.Lock()
        self._started = False
        self._stopped = False
        self._playwright_available: Optional[bool] = None  # cached after first check

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Pre-warm N browser slots in background threads.

        Non-blocking: returns immediately; slots appear in the queue as they
        finish launching.  Safe to call multiple times (no-op after first).
        """
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

        def _warm_one(_: int) -> None:
            try:
                slot = _launch_slot()
                self._q.put(slot)
                log.debug("BrowserPool: slot :%d ready", slot.display_num)
            except Exception as exc:
                log.warning("BrowserPool: pre-warm failed: %s", exc)

        with ThreadPoolExecutor(max_workers=self._size) as ex:
            futures = [ex.submit(_warm_one, i) for i in range(self._size)]
            # Don't wait — executor exits after submitting, threads continue.
            # Actually ThreadPoolExecutor.__exit__ waits for completion, which
            # is fine: pre-warming completes in background relative to FastAPI
            # startup because this whole method is called from a thread.
            for f in as_completed(futures):
                pass  # propagate exceptions via logging, not raises

        _idle_cleaner = threading.Thread(
            target=self._idle_cleanup_loop, daemon=True, name="browser-pool-idle-cleaner"
        )
        _idle_cleaner.start()
        log.info("BrowserPool: started with %d slots", self._q.qsize())

    def stop(self) -> None:
        """Drain and close all pool slots. Called at FastAPI shutdown."""
        with self._lock:
            self._stopped = True

        closed = 0
        while True:
            try:
                slot = self._q.get_nowait()
                _close_slot(slot)
                closed += 1
            except queue.Empty:
                break

        log.info("BrowserPool: stopped, closed %d slot(s)", closed)

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def fetch_html(self, url: str, delay: float = 1.0) -> str:
        """Navigate to *url* and return the rendered HTML.

        Borrows a browser context from the pool (blocks up to 3s), uses it to
        fetch the page, then replenishes the slot with a fresh context.

        Falls back to a fully fresh browser if the pool is empty after the
        timeout or if Playwright is unavailable.
        """
        time.sleep(delay)

        slot: Optional[_PooledBrowser] = None
        try:
            slot = self._q.get(timeout=_QUEUE_TIMEOUT_SECS)
        except queue.Empty:
            log.debug("BrowserPool: pool empty after %.1fs — using fresh browser", _QUEUE_TIMEOUT_SECS)

        if slot is not None:
            try:
                html = self._fetch_with_slot(slot, url)
                # Replenish: close dirty context, open fresh one, return to queue.
                try:
                    fresh_slot = _replenish_slot(slot)
                    self._q.put(fresh_slot)
                except Exception as exc:
                    log.warning("BrowserPool: replenish failed, slot discarded: %s", exc)
                    _close_slot(slot)
                return html
            except Exception as exc:
                log.warning("BrowserPool: pooled fetch failed (%s) — closing slot", exc)
                _close_slot(slot)
                # Fall through to fresh browser below.

        # Fallback: fresh browser (same code as old scraper._fetch_url).
        return self._fetch_fresh(url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_playwright(self) -> bool:
        """Return True if Playwright and Xvfb are importable/runnable."""
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            import playwright  # noqa: F401
            from playwright_stealth import Stealth  # noqa: F401
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    def _fetch_with_slot(self, slot: _PooledBrowser, url: str) -> str:
        """Open a new page on *slot.ctx*, navigate to *url*, return HTML."""
        from playwright_stealth import Stealth

        page = slot.ctx.new_page()
        try:
            Stealth().apply_stealth_sync(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2000)
            return page.content()
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _fetch_fresh(self, url: str) -> str:
        """Launch a fully fresh browser, fetch *url*, close everything."""
        import subprocess as _subprocess

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
        except ImportError as exc:
            raise RuntimeError(
                "Playwright not installed — cannot fetch eBay pages. "
                "Install playwright and playwright-stealth in the Docker image."
            ) from exc

        display_num = next(_pool_display_counter)
        display = f":{display_num}"
        env = os.environ.copy()
        env["DISPLAY"] = display

        xvfb = _subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x800x24"],
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
        )
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
                page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
        finally:
            xvfb.terminate()
            xvfb.wait()

        return html

    def _idle_cleanup_loop(self) -> None:
        """Daemon thread: drain slots idle for >5 minutes every 60 seconds."""
        while not self._stopped:
            time.sleep(_CLEANUP_INTERVAL_SECS)
            if self._stopped:
                break
            now = time.time()
            idle_cutoff = now - _IDLE_TIMEOUT_SECS
            # Drain the entire queue, keep non-idle slots, close idle ones.
            kept: list[_PooledBrowser] = []
            closed = 0
            while True:
                try:
                    slot = self._q.get_nowait()
                except queue.Empty:
                    break
                if slot.last_used_ts < idle_cutoff:
                    _close_slot(slot)
                    closed += 1
                else:
                    kept.append(slot)
            for slot in kept:
                self._q.put(slot)
            if closed:
                log.info("BrowserPool: idle cleanup closed %d slot(s)", closed)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_pool() -> BrowserPool:
    """Return the module-level BrowserPool singleton (creates it if needed).

    Pool size is read from ``BROWSER_POOL_SIZE`` env var (default: 2).
    Call ``get_pool().start()`` at FastAPI startup to pre-warm slots.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                size = int(os.environ.get("BROWSER_POOL_SIZE", "2"))
                _pool = BrowserPool(size)
    return _pool
