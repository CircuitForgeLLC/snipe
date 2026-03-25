"""Render a single listing row with trust score, badges, and error states."""
from __future__ import annotations
import json
import streamlit as st
from app.db.models import Listing, TrustScore, Seller
from typing import Optional


def _score_colour(score: int) -> str:
    if score >= 80: return "🟢"
    if score >= 50: return "🟡"
    return "🔴"


def _flag_label(flag: str) -> str:
    labels = {
        "new_account":            "✗ New account",
        "account_under_30_days":  "⚠ Account <30d",
        "low_feedback_count":     "⚠ Low feedback",
        "suspicious_price":       "✗ Suspicious price",
        "duplicate_photo":        "✗ Duplicate photo",
        "established_bad_actor":  "✗ Bad actor",
        "marketing_photo":        "✗ Marketing photo",
    }
    return labels.get(flag, f"⚠ {flag}")


def render_listing_row(
    listing: Listing,
    trust: Optional[TrustScore],
    seller: Optional[Seller] = None,
) -> None:
    col_img, col_info, col_score = st.columns([1, 5, 2])

    with col_img:
        if listing.photo_urls:
            # Spec requires graceful 404 handling: show placeholder on failure
            try:
                import requests as _req
                r = _req.head(listing.photo_urls[0], timeout=3, allow_redirects=True)
                if r.status_code == 200:
                    st.image(listing.photo_urls[0], width=80)
                else:
                    st.markdown("📷 *Photo unavailable*")
            except Exception:
                st.markdown("📷 *Photo unavailable*")
        else:
            st.markdown("📷 *No photo*")

    with col_info:
        st.markdown(f"**{listing.title}**")
        if seller:
            age_str = f"{seller.account_age_days // 365}yr" if seller.account_age_days >= 365 \
                      else f"{seller.account_age_days}d"
            st.caption(
                f"{seller.username} · {seller.feedback_count} fb · "
                f"{seller.feedback_ratio*100:.1f}% · member {age_str}"
            )
        else:
            st.caption(f"{listing.seller_platform_id} · *Seller data unavailable*")

        if trust:
            flags = json.loads(trust.red_flags_json or "[]")
            if flags:
                badge_html = " ".join(
                    f'<span style="background:#c33;color:#fff;padding:1px 5px;'
                    f'border-radius:3px;font-size:11px">{_flag_label(f)}</span>'
                    for f in flags
                )
                st.markdown(badge_html, unsafe_allow_html=True)
            if trust.score_is_partial:
                st.caption("⚠ Partial score — some data unavailable")
        else:
            st.caption("⚠ Could not score this listing")

    with col_score:
        if trust:
            icon = _score_colour(trust.composite_score)
            st.metric(label="Trust", value=f"{icon} {trust.composite_score}")
        else:
            st.metric(label="Trust", value="?")
        st.markdown(f"**${listing.price:,.0f}**")
        st.markdown(f"[Open eBay ↗]({listing.url})")

    st.divider()
