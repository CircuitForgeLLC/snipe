"""Build dynamic filter options from a result set and render the Streamlit sidebar."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional
import streamlit as st
from app.db.models import Listing, TrustScore


@dataclass
class FilterOptions:
    price_min: float
    price_max: float
    conditions: dict[str, int]        # condition → count
    score_bands: dict[str, int]       # safe/review/skip → count
    has_real_photo: int = 0
    has_em_bag: int = 0
    duplicate_count: int = 0
    new_account_count: int = 0
    free_shipping_count: int = 0


@dataclass
class FilterState:
    min_trust_score: int = 0
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_account_age_days: int = 0
    min_feedback_count: int = 0
    min_feedback_ratio: float = 0.0
    conditions: list[str] = field(default_factory=list)
    hide_new_accounts: bool = False
    hide_marketing_photos: bool = False
    hide_suspicious_price: bool = False
    hide_duplicate_photos: bool = False
    must_include: str = ""
    must_include_mode: str = "all"   # "all" | "any" | "groups"
    must_exclude: str = ""


def build_filter_options(
    pairs: list[tuple[Listing, TrustScore]],
) -> FilterOptions:
    prices = [l.price for l, _ in pairs if l.price > 0]
    conditions: dict[str, int] = {}
    safe = review = skip = 0
    dup_count = new_acct = 0

    for listing, ts in pairs:
        cond = listing.condition or "unknown"
        conditions[cond] = conditions.get(cond, 0) + 1
        if ts.composite_score >= 80:
            safe += 1
        elif ts.composite_score >= 50:
            review += 1
        else:
            skip += 1
        if ts.photo_hash_duplicate:
            dup_count += 1
        flags = json.loads(ts.red_flags_json or "[]")
        if "new_account" in flags or "account_under_30_days" in flags:
            new_acct += 1

    return FilterOptions(
        price_min=min(prices) if prices else 0,
        price_max=max(prices) if prices else 0,
        conditions=conditions,
        score_bands={"safe": safe, "review": review, "skip": skip},
        duplicate_count=dup_count,
        new_account_count=new_acct,
    )


def render_filter_sidebar(
    pairs: list[tuple[Listing, TrustScore]],
    opts: FilterOptions,
) -> FilterState:
    """Render filter sidebar and return current FilterState."""
    state = FilterState()

    st.sidebar.markdown("### Filters")
    st.sidebar.caption(f"{len(pairs)} results")

    st.sidebar.markdown("**Keywords**")
    state.must_include_mode = st.sidebar.radio(
        "Must include mode",
        options=["all", "any", "groups"],
        format_func=lambda m: {"all": "All (AND)", "any": "Any (OR)", "groups": "Groups (CNF)"}[m],
        horizontal=True,
        key="include_mode",
        label_visibility="collapsed",
    )
    hint = {
        "all": "Every term must appear",
        "any": "At least one term must appear",
        "groups": "Comma = AND · pipe | = OR within group",
    }[state.must_include_mode]
    state.must_include = st.sidebar.text_input(
        "Must include", value="", placeholder="16gb, founders…" if state.must_include_mode != "groups" else "founders|fe, 16gb…",
        key="must_include",
    )
    st.sidebar.caption(hint)
    state.must_exclude = st.sidebar.text_input(
        "Must exclude", value="", placeholder="broken, parts…", key="must_exclude",
    )

    state.min_trust_score = st.sidebar.slider("Min trust score", 0, 100, 0, key="min_trust")
    st.sidebar.caption(
        f"🟢 Safe (80+): {opts.score_bands['safe']}  "
        f"🟡 Review (50–79): {opts.score_bands['review']}  "
        f"🔴 Skip (<50): {opts.score_bands['skip']}"
    )

    st.sidebar.markdown("**Price**")
    col1, col2 = st.sidebar.columns(2)
    state.min_price = col1.number_input("Min $", value=opts.price_min, step=50.0, key="min_p")
    state.max_price = col2.number_input("Max $", value=opts.price_max, step=50.0, key="max_p")

    state.min_account_age_days = st.sidebar.slider(
        "Account age (min days)", 0, 365, 0, key="age")
    state.min_feedback_count = st.sidebar.slider(
        "Feedback count (min)", 0, 500, 0, key="fb_count")
    state.min_feedback_ratio = st.sidebar.slider(
        "Positive feedback % (min)", 0, 100, 0, key="fb_ratio") / 100.0

    if opts.conditions:
        st.sidebar.markdown("**Condition**")
        selected = []
        for cond, count in sorted(opts.conditions.items()):
            if st.sidebar.checkbox(f"{cond} ({count})", value=True, key=f"cond_{cond}"):
                selected.append(cond)
        state.conditions = selected

    st.sidebar.markdown("**Hide if flagged**")
    state.hide_new_accounts = st.sidebar.checkbox(
        f"New account (<30d) ({opts.new_account_count})", key="hide_new")
    state.hide_suspicious_price = st.sidebar.checkbox("Suspicious price", key="hide_price")
    state.hide_duplicate_photos = st.sidebar.checkbox(
        f"Duplicate photo ({opts.duplicate_count})", key="hide_dup")

    if st.sidebar.button("Reset filters", key="reset"):
        st.rerun()

    return state
