"""Easter egg features for Snipe.

Three features:
  1. Konami code → Snipe Mode  — JS detector sets ?snipe_mode=1 URL param,
     Streamlit detects it on rerun.  Audio is synthesised client-side via Web
     Audio API (no bundled file; local-first friendly).  Disabled by default
     for accessibility / autoplay-policy reasons; requires explicit sidebar opt-in.

  2. The Steal shimmer  — a listing with trust ≥ 90, price 15–30 % below market,
     and no suspicious_price flag gets a gold shimmer banner.

  3. Auction de-emphasis  — auctions with > 1 h remaining show a soft notice
     because live prices are misleading until the final minutes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from app.db.models import Listing, TrustScore


# ---------------------------------------------------------------------------
# 1. Konami → Snipe Mode
# ---------------------------------------------------------------------------

_KONAMI_JS = """
<script>
(function () {
  const SEQ = [38,38,40,40,37,39,37,39,66,65];
  let idx = 0;
  document.addEventListener('keydown', function (e) {
    if (e.keyCode === SEQ[idx]) {
      idx++;
      if (idx === SEQ.length) {
        idx = 0;
        const url = new URL(window.location.href);
        url.searchParams.set('snipe_mode', '1');
        window.location.href = url.toString();
      }
    } else {
      idx = (e.keyCode === SEQ[0]) ? 1 : 0;
    }
  });
})();
</script>
"""

_SNIPE_AUDIO_JS = """
<script>
(function () {
  if (window.__snipeAudioPlayed) return;
  window.__snipeAudioPlayed = true;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    // Short "sniper scope click" — high sine blip followed by a lower resonant hit
    function blip(freq, start, dur, gain) {
      const osc = ctx.createOscillator();
      const env = ctx.createGain();
      osc.connect(env); env.connect(ctx.destination);
      osc.type = 'sine'; osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
      env.gain.setValueAtTime(0, ctx.currentTime + start);
      env.gain.linearRampToValueAtTime(gain, ctx.currentTime + start + 0.01);
      env.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
      osc.start(ctx.currentTime + start);
      osc.stop(ctx.currentTime + start + dur + 0.05);
    }
    blip(880, 0.00, 0.08, 0.3);
    blip(440, 0.10, 0.15, 0.2);
    blip(220, 0.20, 0.25, 0.15);
  } catch (e) { /* AudioContext blocked — silent fail */ }
})();
</script>
"""

_SNIPE_BANNER_CSS = """
<style>
@keyframes snipe-scan {
  0%   { background-position: -200% center; }
  100% { background-position: 200% center; }
}
.snipe-mode-banner {
  background: linear-gradient(
    90deg,
    #0d1117 0%, #0d1117 40%,
    #39ff14 50%,
    #0d1117 60%, #0d1117 100%
  );
  background-size: 200% auto;
  animation: snipe-scan 2s linear infinite;
  color: #39ff14;
  font-family: monospace;
  font-size: 13px;
  letter-spacing: 0.15em;
  padding: 6px 16px;
  border-radius: 4px;
  margin-bottom: 10px;
  text-align: center;
  text-shadow: 0 0 8px #39ff14;
}
</style>
"""


def inject_konami_detector() -> None:
    """Inject the JS Konami sequence detector into the page (once per load)."""
    st.components.v1.html(_KONAMI_JS, height=0)


def check_snipe_mode() -> bool:
    """Return True if ?snipe_mode=1 is present in the URL query params."""
    return st.query_params.get("snipe_mode", "") == "1"


def render_snipe_mode_banner(audio_enabled: bool) -> None:
    """Render the Snipe Mode activation banner and optionally play the audio cue."""
    st.markdown(_SNIPE_BANNER_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="snipe-mode-banner">🎯 SNIPE MODE ACTIVATED — TARGET ACQUIRED</div>',
        unsafe_allow_html=True,
    )
    if audio_enabled:
        st.components.v1.html(_SNIPE_AUDIO_JS, height=0)


# ---------------------------------------------------------------------------
# 2. The Steal shimmer
# ---------------------------------------------------------------------------

_STEAL_CSS = """
<style>
@keyframes steal-glow {
  0%   { box-shadow: 0 0 6px 1px rgba(255,215,0,0.5); }
  50%  { box-shadow: 0 0 18px 4px rgba(255,215,0,0.9); }
  100% { box-shadow: 0 0 6px 1px rgba(255,215,0,0.5); }
}
.steal-banner {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255,215,0,0.12) 30%,
    rgba(255,215,0,0.35) 50%,
    rgba(255,215,0,0.12) 70%,
    transparent 100%
  );
  border: 1px solid rgba(255,215,0,0.6);
  animation: steal-glow 2.2s ease-in-out infinite;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  color: #ffd700;
  font-weight: 600;
  margin-bottom: 6px;
  letter-spacing: 0.05em;
}
</style>
"""


def inject_steal_css() -> None:
    """Inject the steal-shimmer CSS (idempotent — Streamlit deduplicates)."""
    st.markdown(_STEAL_CSS, unsafe_allow_html=True)


def is_steal(listing: Listing, trust: Optional[TrustScore], market_price: Optional[float]) -> bool:
    """Return True when this listing qualifies as 'The Steal'.

    Criteria (all must hold):
      - trust composite ≥ 90
      - no suspicious_price flag
      - price is 15–30 % below the market median
        (deeper discounts are suspicious, not steals)
    """
    if trust is None or market_price is None or market_price <= 0:
        return False
    if trust.composite_score < 90:
        return False
    flags = json.loads(trust.red_flags_json or "[]")
    if "suspicious_price" in flags:
        return False
    discount = (market_price - listing.price) / market_price
    return 0.15 <= discount <= 0.30


def render_steal_banner() -> None:
    """Render the gold shimmer steal banner above a listing row."""
    st.markdown(
        '<div class="steal-banner">✦ THE STEAL — significantly below market, high trust</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 3. Auction de-emphasis
# ---------------------------------------------------------------------------

def auction_hours_remaining(listing: Listing) -> Optional[float]:
    """Return hours remaining for an auction listing, or None for fixed-price / no data."""
    if listing.buying_format != "auction" or not listing.ends_at:
        return None
    try:
        ends = datetime.fromisoformat(listing.ends_at)
        delta = ends - datetime.now(timezone.utc)
        return max(delta.total_seconds() / 3600, 0.0)
    except (ValueError, TypeError):
        return None


def render_auction_notice(hours: float) -> None:
    """Render a soft de-emphasis notice for auctions with significant time remaining."""
    if hours >= 1.0:
        h = int(hours)
        label = f"{h}h left" if h < 24 else f"{h // 24}d {h % 24}h left"
        st.caption(
            f"⏰ Auction · {label} — price not final until last few minutes"
        )
