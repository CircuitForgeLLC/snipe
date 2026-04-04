"""Snipe feature gates. Delegates to circuitforge_core.tiers.

Tier ladder: free < paid < premium
Ultra is not used in Snipe — auto-bidding is the highest-impact feature and is Premium.

BYOK unlock analog: LOCAL_VISION_UNLOCKABLE — photo_analysis and serial_number_check
unlock when the user has a local vision model (moondream2 (MD2) or equivalent).

Intentionally ungated (free for all):
  - metadata_trust_scoring  — core value prop; wide adoption preferred
  - hash_dedup              — infrastructure, not a differentiator
  - market_comps            — useful enough to drive signups; not scarce
  - scammer_db              — community data is more valuable with wider reach
  - saved_searches          — retention feature; friction cost outweighs gate value
"""
from __future__ import annotations
from circuitforge_core.tiers import can_use as _core_can_use, TIERS  # noqa: F401

# Feature key → minimum tier required.
FEATURES: dict[str, str] = {
    # Paid tier
    "photo_analysis":            "paid",
    "serial_number_check":       "paid",
    "ai_image_detection":        "paid",
    "reverse_image_search":      "paid",
    "ebay_oauth":                "paid",   # full trust scores via eBay Trading API
    "background_monitoring":     "paid",   # limited at Paid; see LIMITS below

    # Premium tier
    "auto_bidding":              "premium",
}

# Per-feature usage limits by tier. None = unlimited.
# Call get_limit(feature, tier) at enforcement points (e.g. before creating a new monitor).
LIMITS: dict[tuple[str, str], int | None] = {
    ("background_monitoring", "paid"):     5,
    ("background_monitoring", "premium"): 25,
}

# Unlock photo_analysis and serial_number_check when user has a local vision model.
# Same policy as Peregrine's BYOK_UNLOCKABLE: user is providing the compute.
LOCAL_VISION_UNLOCKABLE: frozenset[str] = frozenset({
    "photo_analysis",
    "serial_number_check",
})


def can_use(
    feature: str,
    tier: str = "free",
    has_byok: bool = False,
    has_local_vision: bool = False,
) -> bool:
    if has_local_vision and feature in LOCAL_VISION_UNLOCKABLE:
        return True
    return _core_can_use(feature, tier, has_byok=has_byok, _features=FEATURES)


def get_limit(feature: str, tier: str) -> int | None:
    """Return the usage limit for a feature at the given tier.

    Returns None if the feature is unlimited at this tier.
    Returns None if the feature has no entry in LIMITS (treat as unlimited).
    Call can_use() first — get_limit() does not check tier eligibility.

    Example:
        if can_use("background_monitoring", tier):
            limit = get_limit("background_monitoring", tier)
            if limit is not None and current_count >= limit:
                raise LimitExceeded(f"Paid tier allows {limit} active monitors. Upgrade to Premium for unlimited.")
    """
    return LIMITS.get((feature, tier))
