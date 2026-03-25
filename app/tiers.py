"""Snipe feature gates. Delegates to circuitforge_core.tiers."""
from __future__ import annotations
from circuitforge_core.tiers import can_use as _core_can_use, TIERS  # noqa: F401

# Feature key → minimum tier required.
FEATURES: dict[str, str] = {
    # Free tier
    "metadata_trust_scoring":    "free",
    "hash_dedup":                "free",
    # Paid tier
    "photo_analysis":            "paid",
    "serial_number_check":       "paid",
    "ai_image_detection":        "paid",
    "reverse_image_search":      "paid",
    "saved_searches":            "paid",
    "background_monitoring":     "paid",
}

# Photo analysis features unlock if user has local vision model (moondream2 (MD2) or similar).
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
