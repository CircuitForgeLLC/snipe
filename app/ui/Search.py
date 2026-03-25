"""Main search + results page."""
from __future__ import annotations
import logging
import os
from pathlib import Path
import streamlit as st
from circuitforge_core.config import load_env
from app.db.store import Store
from app.platforms import PlatformAdapter, SearchFilters
from app.trust import TrustScorer
from app.ui.components.filters import build_filter_options, render_filter_sidebar, FilterState
from app.ui.components.listing_row import render_listing_row
from app.ui.components.easter_eggs import (
    inject_steal_css, check_snipe_mode, render_snipe_mode_banner,
    auction_hours_remaining,
)

log = logging.getLogger(__name__)

load_env(Path(".env"))
_DB_PATH = Path(os.environ.get("SNIPE_DB", "data/snipe.db"))
_DB_PATH.parent.mkdir(exist_ok=True)


def _get_adapter(store: Store) -> PlatformAdapter:
    """Return the best available eBay adapter based on what's configured.

    Auto-detects: if EBAY_CLIENT_ID + EBAY_CLIENT_SECRET are present, use the
    full API adapter (all 5 trust signals). Otherwise fall back to the scraper
    (3/5 signals, score_is_partial=True) and warn to logs so ops can see why
    scores are partial without touching the UI.
    """
    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()

    if client_id and client_secret:
        from app.platforms.ebay.adapter import EbayAdapter
        from app.platforms.ebay.auth import EbayTokenManager
        env = os.environ.get("EBAY_ENV", "production")
        return EbayAdapter(EbayTokenManager(client_id, client_secret, env), store, env=env)

    log.warning(
        "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set — "
        "falling back to scraper (partial trust scores: account_age and "
        "category_history signals unavailable). Set API credentials for full scoring."
    )
    from app.platforms.ebay.scraper import ScrapedEbayAdapter
    return ScrapedEbayAdapter(store)


def _passes_filter(listing, trust, seller, state: FilterState) -> bool:
    import json
    if trust and trust.composite_score < state.min_trust_score:
        return False
    if state.min_price and listing.price < state.min_price:
        return False
    if state.max_price and listing.price > state.max_price:
        return False
    if state.conditions and listing.condition not in state.conditions:
        return False
    if seller:
        if seller.account_age_days < state.min_account_age_days:
            return False
        if seller.feedback_count < state.min_feedback_count:
            return False
        if seller.feedback_ratio < state.min_feedback_ratio:
            return False
    if trust:
        flags = json.loads(trust.red_flags_json or "[]")
        if state.hide_new_accounts and "account_under_30_days" in flags:
            return False
        if state.hide_suspicious_price and "suspicious_price" in flags:
            return False
        if state.hide_duplicate_photos and "duplicate_photo" in flags:
            return False
    return True


def render(audio_enabled: bool = False) -> None:
    inject_steal_css()

    if check_snipe_mode():
        render_snipe_mode_banner(audio_enabled)

    st.title("🔍 Snipe — eBay Listing Search")

    col_q, col_price, col_btn = st.columns([4, 2, 1])
    query = col_q.text_input("Search", placeholder="RTX 4090 GPU", label_visibility="collapsed")
    max_price = col_price.number_input("Max price $", min_value=0.0, value=0.0,
                                       step=50.0, label_visibility="collapsed")
    search_clicked = col_btn.button("Search", use_container_width=True)

    if not search_clicked or not query:
        st.info("Enter a search term and click Search.")
        return

    store = Store(_DB_PATH)
    adapter = _get_adapter(store)

    with st.spinner("Fetching listings..."):
        try:
            filters = SearchFilters(max_price=max_price if max_price > 0 else None)
            listings = adapter.search(query, filters)
            adapter.get_completed_sales(query)  # warm the comps cache
        except Exception as e:
            st.error(f"eBay search failed: {e}")
            return

    if not listings:
        st.warning("No listings found.")
        return

    for listing in listings:
        store.save_listing(listing)
        if listing.seller_platform_id:
            seller = adapter.get_seller(listing.seller_platform_id)
            if seller:
                store.save_seller(seller)

    scorer = TrustScorer(store)
    trust_scores = scorer.score_batch(listings, query)
    pairs = list(zip(listings, trust_scores))

    opts = build_filter_options(pairs)
    filter_state = render_filter_sidebar(pairs, opts)

    sort_col = st.selectbox(
        "Sort by",
        ["Trust score", "Price ↑", "Price ↓", "Newest", "Ending soon"],
        label_visibility="collapsed",
    )

    def sort_key(pair):
        l, t = pair
        if sort_col == "Trust score":  return -(t.composite_score if t else 0)
        if sort_col == "Price ↑":      return l.price
        if sort_col == "Price ↓":      return -l.price
        if sort_col == "Ending soon":
            h = auction_hours_remaining(l)
            # Non-auctions sort to end; auctions sort ascending by time left
            return (h if h is not None else float("inf"))
        return l.listing_age_days

    sorted_pairs = sorted(pairs, key=sort_key)
    visible = [(l, t) for l, t in sorted_pairs
               if _passes_filter(l, t, store.get_seller("ebay", l.seller_platform_id), filter_state)]
    hidden_count = len(sorted_pairs) - len(visible)

    st.caption(f"{len(visible)} results · {hidden_count} hidden by filters")

    import hashlib
    query_hash = hashlib.md5(query.encode()).hexdigest()
    comp = store.get_market_comp("ebay", query_hash)
    market_price = comp.median_price if comp else None

    for listing, trust in visible:
        seller = store.get_seller("ebay", listing.seller_platform_id)
        render_listing_row(listing, trust, seller, market_price=market_price)

    if hidden_count:
        if st.button(f"Show {hidden_count} hidden results"):
            visible_ids = {(l.platform, l.platform_listing_id) for l, _ in visible}
            for listing, trust in sorted_pairs:
                if (listing.platform, listing.platform_listing_id) not in visible_ids:
                    seller = store.get_seller("ebay", listing.seller_platform_id)
                    render_listing_row(listing, trust, seller, market_price=market_price)
