"""Reproduce the exact FastAPI code path: pool warmup → slot close → _fetch_fresh.

Run inside the container:
    docker exec -it snipe-api-1 python /app/snipe/scripts/debug_fetch_fresh.py
"""
import sys
import threading
import time

sys.path.insert(0, '/app/snipe')

from bs4 import BeautifulSoup

from app.platforms.ebay.browser_pool import BrowserPool, _close_slot

URL = "https://www.mercari.com/search/?keyword=rtx+4090&sortBy=SORT_SCORE&priceMax=800"

print("=== Test 1: _fetch_fresh with no pool (baseline) ===", flush=True)
pool0 = BrowserPool(size=0)
t0 = time.time()
html = pool0._fetch_fresh(URL, wait_for_timeout_ms=8000)
items = BeautifulSoup(html, "html.parser").find_all(attrs={"data-testid": "ItemContainer"})
print(f"Items: {len(items)}, HTML: {len(html)}b, elapsed: {time.time()-t0:.1f}s", flush=True)

print("\n=== Test 2: pool warmup (size=2), grab slot, close it, then _fetch_fresh ===", flush=True)
pool2 = BrowserPool(size=2)

# Warmup in background (blocks until done)
warm_done = threading.Event()
def do_warmup():
    pool2.start()
    warm_done.set()

t = threading.Thread(target=do_warmup, daemon=True)
t.start()
warm_done.wait(timeout=30)
print(f"Pool size after warmup: {pool2._q.qsize()}", flush=True)

# Grab a slot and close it (simulating the thread-error path)
import queue

try:
    slot = pool2._q.get(timeout=3.0)
    print(f"Got slot on display :{slot.display_num}", flush=True)
    _close_slot(slot)
    print("Slot closed", flush=True)
except queue.Empty:
    print("Pool empty — no slot to simulate", flush=True)

# Now call _fetch_fresh in this thread (same as FastAPI handler thread)
print("Calling _fetch_fresh from warmup-thread context...", flush=True)
t0 = time.time()
html2 = pool2._fetch_fresh(URL, wait_for_timeout_ms=8000)
items2 = BeautifulSoup(html2, "html.parser").find_all(attrs={"data-testid": "ItemContainer"})
print(f"Items: {len(items2)}, HTML: {len(html2)}b, elapsed: {time.time()-t0:.1f}s", flush=True)

# Save HTML for inspection if empty
if len(items2) == 0:
    with open("/tmp/debug_mercari.html", "w") as f:
        f.write(html2)
    print("Saved HTML to /tmp/debug_mercari.html", flush=True)
    title = BeautifulSoup(html2, "html.parser").find("title")
    print("Page title:", title.get_text() if title else "(none)", flush=True)
    if "Just a moment" in html2 or "turnstile" in html2.lower():
        print("BLOCKED: Cloudflare challenge", flush=True)
    else:
        body = BeautifulSoup(html2, "html.parser").find("body")
        if body:
            print("Body snippet:", body.get_text(separator=" ", strip=True)[:300], flush=True)
