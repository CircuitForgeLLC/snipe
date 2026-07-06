"""One-shot Mercari probe using the same headed Chromium + Xvfb + stealth stack
as the eBay scraper.  Run inside the snipe-api container:

    docker exec -it snipe-api-1 python /app/scripts/probe_mercari.py
"""
from __future__ import annotations

import itertools
import os
import subprocess
import time

_display_counter = itertools.count(200)
_CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

SEARCH_URL = "https://www.mercari.com/search/?keyword=rtx+4090"
# Give Cloudflare challenge time to resolve (if it does)
WAIT_MS = 8_000


def probe(url: str) -> str:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    display_num = next(_display_counter)
    display = f":{display_num}"
    env = os.environ.copy()
    env["DISPLAY"] = display

    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                env=env,
                args=_CHROMIUM_ARGS,
            )
            ctx = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            Stealth().apply_stealth_sync(page)
            print(f"[probe] Navigating to {url} …", flush=True)
            response = page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            print(f"[probe] HTTP status: {response.status if response else 'unknown'}", flush=True)
            print(f"[probe] Waiting {WAIT_MS}ms for JS / Turnstile …", flush=True)
            page.wait_for_timeout(WAIT_MS)
            html = page.content()
            title = page.title()
            print(f"[probe] Page title: {title!r}", flush=True)
            browser.close()
    finally:
        xvfb.terminate()
        xvfb.wait()

    return html


def analyse(html: str) -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Cloudflare challenge indicators
    if "Just a moment" in html or "cf-challenge" in html or "turnstile" in html.lower():
        print("[result] BLOCKED — Cloudflare Turnstile still active")
        return

    print("[result] Cloudflare challenge NOT detected — page appears to have loaded")

    # Try to find listing cards
    # Mercari US uses data-testid or item cards in the DOM
    candidates = [
        soup.select("[data-testid='ItemCell']"),
        soup.select("[data-testid='item-cell']"),
        soup.select("li[data-testid]"),
        soup.select(".merList .merListItem"),
        soup.select("[class*='ItemCell']"),
        soup.select("[class*='item-cell']"),
    ]
    for sel_result in candidates:
        if sel_result:
            print(f"[result] Found {len(sel_result)} listing card(s) via selector")
            card = sel_result[0]
            print(f"[result] First card snippet:\n{card.prettify()[:800]}")
            return

    # Fallback: show body text summary
    body = soup.find("body")
    text = body.get_text(separator=" ", strip=True)[:500] if body else html[:500]
    print(f"[result] No listing cards found. Body text preview:\n{text}")
    # Save full HTML for manual inspection
    out = "/tmp/mercari_probe.html"
    with open(out, "w") as fh:
        fh.write(html)
    print(f"[result] Full HTML saved to {out}")


if __name__ == "__main__":
    html = probe(SEARCH_URL)
    analyse(html)
