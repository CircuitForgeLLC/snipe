"""Snipe FastAPI — search endpoint wired to ScrapedEbayAdapter + TrustScorer."""
from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import csv
import io

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from circuitforge_core.config import load_env
from circuitforge_core.affiliates import wrap_url as _wrap_affiliate_url
from circuitforge_core.api import make_feedback_router as _make_feedback_router
from app.db.store import Store
from app.db.models import SavedSearch as SavedSearchModel, ScammerEntry
from app.platforms import SearchFilters
from app.platforms.ebay.scraper import ScrapedEbayAdapter
from app.platforms.ebay.adapter import EbayAdapter
from app.platforms.ebay.auth import EbayTokenManager
from app.platforms.ebay.query_builder import expand_queries, parse_groups
from app.trust import TrustScorer
from api.cloud_session import CloudUser, compute_features, get_session
from api.ebay_webhook import router as ebay_webhook_router

load_env(Path(".env"))
log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Start vision/LLM background task scheduler.
    # background_tasks queue lives in shared_db (cloud) or local_db (local)
    # so the scheduler has a single stable DB path across all cloud users.
    from app.tasks.scheduler import get_scheduler, reset_scheduler
    from api.cloud_session import CLOUD_MODE, _LOCAL_SNIPE_DB, _shared_db_path
    sched_db = _shared_db_path() if CLOUD_MODE else _LOCAL_SNIPE_DB
    get_scheduler(sched_db)
    log.info("Snipe task scheduler started (db=%s)", sched_db)
    yield
    get_scheduler(sched_db).shutdown(timeout=10.0)
    reset_scheduler()
    log.info("Snipe task scheduler stopped.")


def _ebay_creds() -> tuple[str, str, str]:
    """Return (client_id, client_secret, env) from env vars.

    New names: EBAY_APP_ID / EBAY_CERT_ID (sandbox: EBAY_SANDBOX_APP_ID / EBAY_SANDBOX_CERT_ID)
    Legacy fallback: EBAY_CLIENT_ID / EBAY_CLIENT_SECRET
    """
    env = os.environ.get("EBAY_ENV", "production").strip()
    if env == "sandbox":
        client_id = os.environ.get("EBAY_SANDBOX_APP_ID", "").strip()
        client_secret = os.environ.get("EBAY_SANDBOX_CERT_ID", "").strip()
    else:
        client_id = (os.environ.get("EBAY_APP_ID") or os.environ.get("EBAY_CLIENT_ID", "")).strip()
        client_secret = (os.environ.get("EBAY_CERT_ID") or os.environ.get("EBAY_CLIENT_SECRET", "")).strip()
    return client_id, client_secret, env


app = FastAPI(title="Snipe API", version="0.1.0", lifespan=_lifespan)
app.include_router(ebay_webhook_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_feedback_router = _make_feedback_router(
    repo="Circuit-Forge/snipe",
    product="snipe",
)
app.include_router(_feedback_router, prefix="/api/feedback")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/session")
def session_info(session: CloudUser = Depends(get_session)):
    """Return the current session tier and computed feature flags.

    Used by the Vue frontend to gate UI features (pages slider cap,
    saved search limits, shared DB badges, etc.) without hardcoding
    tier logic client-side.
    """
    features = compute_features(session.tier)
    return {
        "user_id": session.user_id,
        "tier": session.tier,
        "features": dataclasses.asdict(features),
    }


def _trigger_scraper_enrichment(
    listings: list,
    shared_store: Store,
    shared_db: Path,
) -> None:
    """Fire-and-forget background enrichment for missing seller signals.

    Two enrichment passes run concurrently in the same daemon thread:
      1. BTF (/itm/ pages) — fills account_age_days for sellers where it is None.
      2. _ssn search pages  — fills category_history_json for sellers with no history.

    The main response returns immediately; enriched data lands in the DB for
    future searches. Uses ScrapedEbayAdapter's Playwright stack regardless of
    which adapter was used for the main search (Shopping API handles age for
    the API adapter inline; BTF is the fallback for no-creds / scraper mode).

    shared_store: used for pre-flight seller checks (same-thread reads).
    shared_db: path passed to background thread — it creates its own Store
               (sqlite3 connections are not thread-safe).
    """
    # Caps per search: limits Playwright sessions launched in the background so we
    # don't hammer Kasada or spin up dozens of Xvfb instances after a large search.
    # Remaining sellers get enriched incrementally on subsequent searches.
    _BTF_MAX_PER_SEARCH = 3
    _CAT_MAX_PER_SEARCH = 3

    needs_btf: dict[str, str] = {}
    needs_categories: list[str] = []

    for listing in listings:
        sid = listing.seller_platform_id
        if not sid:
            continue
        seller = shared_store.get_seller("ebay", sid)
        if not seller:
            continue
        if ((seller.account_age_days is None or seller.feedback_count == 0)
                and sid not in needs_btf
                and len(needs_btf) < _BTF_MAX_PER_SEARCH):
            needs_btf[sid] = listing.platform_listing_id
        if (seller.category_history_json in ("{}", "", None)
                and sid not in needs_categories
                and len(needs_categories) < _CAT_MAX_PER_SEARCH):
            needs_categories.append(sid)

    if not needs_btf and not needs_categories:
        return

    log.info(
        "Scraper enrichment: %d BTF age + %d category pages queued",
        len(needs_btf), len(needs_categories),
    )

    def _run():
        try:
            enricher = ScrapedEbayAdapter(Store(shared_db))
            if needs_btf:
                enricher.enrich_sellers_btf(needs_btf, max_workers=2)
                log.info("BTF enrichment complete for %d sellers", len(needs_btf))
            if needs_categories:
                enricher.enrich_sellers_categories(needs_categories, max_workers=2)
                log.info("Category enrichment complete for %d sellers", len(needs_categories))
        except Exception as e:
            log.warning("Scraper enrichment failed: %s", e)

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _enqueue_vision_tasks(
    listings: list,
    trust_scores_list: list,
    session: "CloudUser",
) -> None:
    """Enqueue trust_photo_analysis tasks for listings with photos.

    Runs fire-and-forget: tasks land in the scheduler queue and the response
    returns immediately.  Results are written back to trust_scores.photo_analysis_json
    by the runner when the vision LLM completes.

    session.shared_db: where background_tasks lives (scheduler's DB).
    session.user_db:   encoded in params so the runner writes to the right
                       trust_scores table in cloud mode.
    """
    import json as _json
    from app.tasks.runner import insert_task
    from app.tasks.scheduler import get_scheduler
    from api.cloud_session import CLOUD_MODE, _shared_db_path, _LOCAL_SNIPE_DB

    sched_db = _shared_db_path() if CLOUD_MODE else _LOCAL_SNIPE_DB
    sched = get_scheduler(sched_db)

    enqueued = 0
    for listing, ts in zip(listings, trust_scores_list):
        if not listing.photo_urls or not listing.id:
            continue
        params = _json.dumps({
            "photo_url": listing.photo_urls[0],
            "listing_title": listing.title,
            "user_db": str(session.user_db),
        })
        task_id, is_new = insert_task(
            sched_db, "trust_photo_analysis", job_id=listing.id, params=params
        )
        if is_new:
            ok = sched.enqueue(task_id, "trust_photo_analysis", listing.id, params)
            if not ok:
                log.warning(
                    "Vision task queue full — dropped task for listing %s",
                    listing.platform_listing_id,
                )
            else:
                enqueued += 1

    if enqueued:
        log.info("Enqueued %d vision analysis task(s)", enqueued)


def _parse_terms(raw: str) -> list[str]:
    """Split a comma-separated keyword string into non-empty, stripped terms."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _make_adapter(shared_store: Store, force: str = "auto"):
    """Return the appropriate adapter.

    force: "auto" | "api" | "scraper"
      auto    — API if creds present, else scraper
      api     — Browse API (raises if no creds)
      scraper — Playwright scraper regardless of creds

    Adapters receive shared_store because they only read/write sellers and
    market_comps — never listings. Listings are returned and saved by the caller.
    """
    client_id, client_secret, env = _ebay_creds()
    has_creds = bool(client_id and client_secret)

    if force == "scraper":
        return ScrapedEbayAdapter(shared_store)
    if force == "api":
        if not has_creds:
            raise ValueError("adapter=api requested but no eBay API credentials configured")
        return EbayAdapter(EbayTokenManager(client_id, client_secret, env), shared_store, env=env)
    # auto
    if has_creds:
        return EbayAdapter(EbayTokenManager(client_id, client_secret, env), shared_store, env=env)
    log.debug("No eBay API credentials — using scraper adapter (partial trust scores)")
    return ScrapedEbayAdapter(shared_store)


def _adapter_name(force: str = "auto") -> str:
    """Return the name of the adapter that would be used — without creating it."""
    client_id, client_secret, _ = _ebay_creds()
    if force == "scraper":
        return "scraper"
    if force == "api" or (force == "auto" and client_id and client_secret):
        return "api"
    return "scraper"


@app.get("/api/search")
def search(
    q: str = "",
    max_price: float = 0,
    min_price: float = 0,
    pages: int = 1,
    must_include: str = "",        # raw filter string; client-side always applied
    must_include_mode: str = "all", # "all" | "any" | "groups" — drives eBay expansion
    must_exclude: str = "",        # comma-separated; forwarded to eBay -term + client-side
    category_id: str = "",         # eBay category ID — forwarded to Browse API / scraper _sacat
    adapter: str = "auto",         # "auto" | "api" | "scraper" — override adapter selection
    session: CloudUser = Depends(get_session),
):
    if not q.strip():
        return {"listings": [], "trust_scores": {}, "sellers": {}, "market_price": None, "adapter_used": _adapter_name(adapter)}

    # Cap pages to the tier's maximum — free cloud users get 1 page, local gets unlimited.
    features = compute_features(session.tier)
    pages = min(max(1, pages), features.max_pages)

    must_exclude_terms = _parse_terms(must_exclude)

    # In Groups mode, expand OR groups into multiple targeted eBay queries to
    # guarantee comprehensive result coverage — eBay relevance won't silently drop variants.
    if must_include_mode == "groups" and must_include.strip():
        or_groups = parse_groups(must_include)
        ebay_queries = expand_queries(q, or_groups)
    else:
        ebay_queries = [q]

    base_filters = SearchFilters(
        max_price=max_price if max_price > 0 else None,
        min_price=min_price if min_price > 0 else None,
        pages=pages,
        must_exclude=must_exclude_terms,  # forwarded to eBay -term by the scraper
        category_id=category_id.strip() or None,
    )

    adapter_used = _adapter_name(adapter)

    shared_db = session.shared_db
    user_db = session.user_db

    # Each thread creates its own Store — sqlite3 check_same_thread=True.
    def _run_search(ebay_query: str) -> list:
        return _make_adapter(Store(shared_db), adapter).search(ebay_query, base_filters)

    def _run_comps() -> None:
        try:
            _make_adapter(Store(shared_db), adapter).get_completed_sales(q, pages)
        except Exception:
            log.warning("comps: unhandled exception for %r", q, exc_info=True)

    try:
        # Comps submitted first — guarantees an immediate worker slot even at max concurrency.
        # Seller enrichment runs after the executor exits (background thread), so comps are
        # always prioritised over tracking seller age / category history.
        max_workers = min(len(ebay_queries) + 1, 5)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            comps_future = ex.submit(_run_comps)
            search_futures = [ex.submit(_run_search, eq) for eq in ebay_queries]

            # Merge and deduplicate across all search queries
            seen_ids: set[str] = set()
            listings: list = []
            for fut in search_futures:
                for listing in fut.result():
                    if listing.platform_listing_id not in seen_ids:
                        seen_ids.add(listing.platform_listing_id)
                        listings.append(listing)
            comps_future.result()  # side-effect: market comp written to shared DB
    except Exception as e:
        log.warning("eBay scrape failed: %s", e)
        raise HTTPException(status_code=502, detail=f"eBay search failed: {e}")

    log.info("Multi-search: %d queries → %d unique listings", len(ebay_queries), len(listings))

    # Main-thread stores — fresh connections, same thread.
    # shared_store: sellers, market_comps (all users share this data)
    # user_store: listings, saved_searches (per-user in cloud mode, same file in local mode)
    shared_store = Store(shared_db)
    user_store = Store(user_db)

    user_store.save_listings(listings)

    # Derive category_history from accumulated listing data — free for API adapter
    # (category_name comes from Browse API response), no-op for scraper listings (category_name=None).
    # Reads listings from user_store, writes seller categories to shared_store.
    seller_ids = list({l.seller_platform_id for l in listings if l.seller_platform_id})
    n_cat = shared_store.refresh_seller_categories("ebay", seller_ids, listing_store=user_store)
    if n_cat:
        log.info("Category history derived for %d sellers from listing data", n_cat)

    # Re-fetch to hydrate staging fields (times_seen, first_seen_at, id, price_at_first_seen)
    # that are only available from the DB after the upsert.
    staged = user_store.get_listings_staged("ebay", [l.platform_listing_id for l in listings])
    listings = [staged.get(l.platform_listing_id, l) for l in listings]

    # BTF enrichment: scrape /itm/ pages for sellers missing account_age_days.
    # Runs in the background so it doesn't delay the response; next search of
    # the same sellers will have full scores.
    _trigger_scraper_enrichment(listings, shared_store, shared_db)

    scorer = TrustScorer(shared_store)
    trust_scores_list = scorer.score_batch(listings, q)

    # Persist trust scores so background vision tasks have a row to UPDATE.
    user_store.save_trust_scores(trust_scores_list)

    # Enqueue vision analysis for listings with photos — Paid tier and above.
    features = compute_features(session.tier)
    if features.photo_analysis:
        _enqueue_vision_tasks(listings, trust_scores_list, session)

    query_hash = hashlib.md5(q.encode()).hexdigest()
    comp = shared_store.get_market_comp("ebay", query_hash)
    market_price = comp.median_price if comp else None

    # Serialize — keyed by platform_listing_id for easy Vue lookup
    trust_map = {
        listing.platform_listing_id: dataclasses.asdict(ts)
        for listing, ts in zip(listings, trust_scores_list)
        if ts is not None
    }
    seller_map = {
        listing.seller_platform_id: dataclasses.asdict(
            shared_store.get_seller("ebay", listing.seller_platform_id)
        )
        for listing in listings
        if listing.seller_platform_id
        and shared_store.get_seller("ebay", listing.seller_platform_id)
    }

    def _serialize_listing(l: object) -> dict:
        d = dataclasses.asdict(l)
        d["url"] = _wrap_affiliate_url(d["url"], retailer="ebay")
        return d

    return {
        "listings": [_serialize_listing(l) for l in listings],
        "trust_scores": trust_map,
        "sellers": seller_map,
        "market_price": market_price,
        "adapter_used": adapter_used,
        "affiliate_active": bool(os.environ.get("EBAY_AFFILIATE_CAMPAIGN_ID", "").strip()),
    }


# ── On-demand enrichment ──────────────────────────────────────────────────────

@app.post("/api/enrich")
def enrich_seller(
    seller: str,
    listing_id: str,
    query: str = "",
    session: CloudUser = Depends(get_session),
):
    """Synchronous on-demand enrichment for a single seller + re-score.

    Runs enrichment paths in parallel:
      - Shopping API GetUserProfile (fast, ~500ms) — account_age_days if API creds present
      - BTF /itm/ Playwright scrape (~20s) — account_age_days fallback
      - _ssn Playwright scrape (~20s)     — category_history_json

    BTF and _ssn run concurrently; total wall time ~20s when Playwright needed.
    Returns the updated trust_score and seller so the frontend can patch in-place.
    """
    import threading

    shared_store = Store(session.shared_db)
    user_store = Store(session.user_db)
    shared_db = session.shared_db

    seller_obj = shared_store.get_seller("ebay", seller)
    if not seller_obj:
        raise HTTPException(status_code=404, detail=f"Seller '{seller}' not found")

    # Fast path: Shopping API for account age (inline, no Playwright)
    try:
        api_adapter = _make_adapter(shared_store, "api")
        if hasattr(api_adapter, "enrich_sellers_shopping_api"):
            api_adapter.enrich_sellers_shopping_api([seller])
    except Exception:
        pass  # no API creds — fall through to BTF

    seller_obj = shared_store.get_seller("ebay", seller)
    needs_btf = seller_obj is not None and (
        seller_obj.account_age_days is None or seller_obj.feedback_count == 0
    )
    needs_categories = seller_obj is None or seller_obj.category_history_json in ("{}", "", None)

    # Slow path: Playwright for remaining gaps (BTF + _ssn in parallel threads).
    # Each thread creates its own Store — sqlite3 connections are not thread-safe.
    if needs_btf or needs_categories:
        errors: list[Exception] = []

        def _btf():
            try:
                ScrapedEbayAdapter(Store(shared_db)).enrich_sellers_btf(
                    {seller: listing_id}, max_workers=1
                )
            except Exception as e:
                errors.append(e)

        def _ssn():
            try:
                ScrapedEbayAdapter(Store(shared_db)).enrich_sellers_categories(
                    [seller], max_workers=1
                )
            except Exception as e:
                errors.append(e)

        threads = []
        if needs_btf:
            threads.append(threading.Thread(target=_btf, daemon=True))
        if needs_categories:
            threads.append(threading.Thread(target=_ssn, daemon=True))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        if errors:
            log.warning("enrich_seller: %d scrape error(s): %s", len(errors), errors[0])

    # Re-fetch listing with staging fields, re-score
    staged = user_store.get_listings_staged("ebay", [listing_id])
    listing = staged.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing '{listing_id}' not found")

    scorer = TrustScorer(shared_store)
    trust_list = scorer.score_batch([listing], query or listing.title)
    trust = trust_list[0] if trust_list else None

    seller_final = shared_store.get_seller("ebay", seller)
    return {
        "trust_score": dataclasses.asdict(trust) if trust else None,
        "seller": dataclasses.asdict(seller_final) if seller_final else None,
    }


# ── Saved Searches ────────────────────────────────────────────────────────────

class SavedSearchCreate(BaseModel):
    name: str
    query: str
    filters_json: str = "{}"


@app.get("/api/saved-searches")
def list_saved_searches(session: CloudUser = Depends(get_session)):
    user_store = Store(session.user_db)
    return {"saved_searches": [dataclasses.asdict(s) for s in user_store.list_saved_searches()]}


@app.post("/api/saved-searches", status_code=201)
def create_saved_search(
    body: SavedSearchCreate,
    session: CloudUser = Depends(get_session),
):
    user_store = Store(session.user_db)
    features = compute_features(session.tier)

    if features.saved_searches_limit is not None:
        existing = user_store.list_saved_searches()
        if len(existing) >= features.saved_searches_limit:
            raise HTTPException(
                status_code=403,
                detail=f"Free tier allows up to {features.saved_searches_limit} saved searches. Upgrade to save more.",
            )

    created = user_store.save_saved_search(
        SavedSearchModel(name=body.name, query=body.query, platform="ebay", filters_json=body.filters_json)
    )
    return dataclasses.asdict(created)


@app.delete("/api/saved-searches/{saved_id}", status_code=204)
def delete_saved_search(saved_id: int, session: CloudUser = Depends(get_session)):
    Store(session.user_db).delete_saved_search(saved_id)


@app.patch("/api/saved-searches/{saved_id}/run")
def mark_saved_search_run(saved_id: int, session: CloudUser = Depends(get_session)):
    Store(session.user_db).update_saved_search_last_run(saved_id)
    return {"ok": True}


# ── Scammer Blocklist ─────────────────────────────────────────────────────────
# Blocklist lives in shared_db: all users on a shared cloud instance see the
# same community blocklist. In local (single-user) mode shared_db == user_db.

class BlocklistAdd(BaseModel):
    platform: str = "ebay"
    platform_seller_id: str
    username: str
    reason: str = ""


@app.get("/api/blocklist")
def list_blocklist(session: CloudUser = Depends(get_session)):
    store = Store(session.shared_db)
    return {"entries": [dataclasses.asdict(e) for e in store.list_blocklist()]}


@app.post("/api/blocklist", status_code=201)
def add_to_blocklist(body: BlocklistAdd, session: CloudUser = Depends(get_session)):
    store = Store(session.shared_db)
    entry = store.add_to_blocklist(ScammerEntry(
        platform=body.platform,
        platform_seller_id=body.platform_seller_id,
        username=body.username,
        reason=body.reason or None,
        source="manual",
    ))
    return dataclasses.asdict(entry)


@app.delete("/api/blocklist/{platform_seller_id}", status_code=204)
def remove_from_blocklist(platform_seller_id: str, session: CloudUser = Depends(get_session)):
    Store(session.shared_db).remove_from_blocklist("ebay", platform_seller_id)


@app.get("/api/blocklist/export")
def export_blocklist(session: CloudUser = Depends(get_session)):
    """Download the blocklist as a CSV file."""
    entries = Store(session.shared_db).list_blocklist()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["platform", "platform_seller_id", "username", "reason", "source", "created_at"])
    for e in entries:
        writer.writerow([e.platform, e.platform_seller_id, e.username,
                         e.reason or "", e.source, e.created_at or ""])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=snipe-blocklist.csv"},
    )


@app.post("/api/blocklist/import", status_code=201)
async def import_blocklist(
    file: UploadFile = File(...),
    session: CloudUser = Depends(get_session),
):
    """Import a CSV blocklist. Columns: platform_seller_id, username, reason (optional)."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM from Excel exports
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    store = Store(session.shared_db)
    imported = 0
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(text))

    # Accept both full-export format (has 'platform' col) and simple format (no 'platform' col).
    for i, row in enumerate(reader, start=2):
        seller_id = (row.get("platform_seller_id") or "").strip()
        username = (row.get("username") or "").strip()
        if not seller_id or not username:
            errors.append(f"Row {i}: missing platform_seller_id or username — skipped")
            continue
        platform = (row.get("platform") or "ebay").strip()
        reason = (row.get("reason") or "").strip() or None
        store.add_to_blocklist(ScammerEntry(
            platform=platform,
            platform_seller_id=seller_id,
            username=username,
            reason=reason,
            source="csv_import",
        ))
        imported += 1

    log.info("Blocklist import: %d added, %d errors", imported, len(errors))
    return {"imported": imported, "errors": errors}


