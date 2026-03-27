"""Cloud session resolution for Snipe FastAPI.

In local mode (CLOUD_MODE unset/false): all functions return a local CloudUser
with no auth checks, full tier access, and both DB paths pointing to SNIPE_DB.

In cloud mode (CLOUD_MODE=true): validates the cf_session JWT injected by Caddy
as X-CF-Session, resolves user_id, auto-provisions a free Heimdall license on
first visit, fetches the tier, and returns per-user DB paths.

FastAPI usage:
    @app.get("/api/search")
    def search(session: CloudUser = Depends(get_session)):
        shared_store = Store(session.shared_db)
        user_store   = Store(session.user_db)
        ...
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from fastapi import Depends, HTTPException, Request

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CLOUD_MODE: bool = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true", "yes")
CLOUD_DATA_ROOT: Path = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/snipe-cloud-data"))
DIRECTUS_JWT_SECRET: str = os.environ.get("DIRECTUS_JWT_SECRET", "")
CF_SERVER_SECRET: str = os.environ.get("CF_SERVER_SECRET", "")
HEIMDALL_URL: str = os.environ.get("HEIMDALL_URL", "https://license.circuitforge.tech")
HEIMDALL_ADMIN_TOKEN: str = os.environ.get("HEIMDALL_ADMIN_TOKEN", "")

# Local-mode DB paths (ignored in cloud mode)
_LOCAL_SNIPE_DB: Path = Path(os.environ.get("SNIPE_DB", "data/snipe.db"))

# Tier cache: user_id → (tier, fetched_at_epoch)
_TIER_CACHE: dict[str, tuple[str, float]] = {}
_TIER_CACHE_TTL = 300  # 5 minutes

TIERS = ["free", "paid", "premium", "ultra"]


# ── Domain ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CloudUser:
    user_id: str    # Directus UUID, or "local" in local mode
    tier: str       # free | paid | premium | ultra | local
    shared_db: Path # sellers, market_comps — shared across all users
    user_db: Path   # listings, saved_searches, trust_scores — per-user


@dataclass(frozen=True)
class SessionFeatures:
    saved_searches: bool
    saved_searches_limit: Optional[int]  # None = unlimited
    background_monitoring: bool
    max_pages: int
    upc_search: bool
    photo_analysis: bool
    shared_scammer_db: bool
    shared_image_db: bool


def compute_features(tier: str) -> SessionFeatures:
    """Compute feature flags from tier. Evaluated server-side; sent to frontend."""
    local = tier == "local"
    paid_plus = local or tier in ("paid", "premium", "ultra")
    premium_plus = local or tier in ("premium", "ultra")

    return SessionFeatures(
        saved_searches=True,  # all tiers get saved searches
        saved_searches_limit=None if paid_plus else 3,
        background_monitoring=paid_plus,
        max_pages=999 if local else (5 if paid_plus else 1),
        upc_search=paid_plus,
        photo_analysis=paid_plus,
        shared_scammer_db=paid_plus,
        shared_image_db=paid_plus,
    )


# ── JWT validation ────────────────────────────────────────────────────────────

def _extract_session_token(header_value: str) -> str:
    """Extract cf_session value from a Cookie or X-CF-Session header string."""
    # X-CF-Session may be the raw JWT or the full cookie string
    m = re.search(r'(?:^|;)\s*cf_session=([^;]+)', header_value)
    return m.group(1).strip() if m else header_value.strip()


def validate_session_jwt(token: str) -> str:
    """Validate a cf_session JWT and return the Directus user_id.

    Uses HMAC-SHA256 verification against DIRECTUS_JWT_SECRET (same secret
    cf-directus uses to sign session tokens). Returns user_id on success,
    raises HTTPException(401) on failure.

    Directus 11+ uses 'id' (not 'sub') for the user UUID in its JWT payload.
    """
    try:
        import jwt as pyjwt
        payload = pyjwt.decode(
            token,
            DIRECTUS_JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["id", "exp"]},
        )
        return payload["id"]
    except Exception as exc:
        log.debug("JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Session invalid or expired")


# ── Heimdall integration ──────────────────────────────────────────────────────

def _ensure_provisioned(user_id: str) -> None:
    """Idempotent: create a free Heimdall license for this user if none exists."""
    if not HEIMDALL_ADMIN_TOKEN:
        return
    try:
        requests.post(
            f"{HEIMDALL_URL}/admin/provision",
            json={"directus_user_id": user_id, "product": "snipe", "tier": "free"},
            headers={"Authorization": f"Bearer {HEIMDALL_ADMIN_TOKEN}"},
            timeout=5,
        )
    except Exception as exc:
        log.warning("Heimdall provision failed for user %s: %s", user_id, exc)


def _fetch_cloud_tier(user_id: str) -> str:
    """Resolve tier from Heimdall with a 5-minute in-process cache."""
    now = time.monotonic()
    cached = _TIER_CACHE.get(user_id)
    if cached and (now - cached[1]) < _TIER_CACHE_TTL:
        return cached[0]

    if not HEIMDALL_ADMIN_TOKEN:
        return "free"
    try:
        resp = requests.post(
            f"{HEIMDALL_URL}/admin/cloud/resolve",
            json={"directus_user_id": user_id, "product": "snipe"},
            headers={"Authorization": f"Bearer {HEIMDALL_ADMIN_TOKEN}"},
            timeout=5,
        )
        tier = resp.json().get("tier", "free") if resp.ok else "free"
    except Exception as exc:
        log.warning("Heimdall tier resolve failed for user %s: %s", user_id, exc)
        tier = "free"

    _TIER_CACHE[user_id] = (tier, now)
    return tier


# ── DB path helpers ───────────────────────────────────────────────────────────

def _shared_db_path() -> Path:
    path = CLOUD_DATA_ROOT / "shared" / "shared.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _user_db_path(user_id: str) -> Path:
    path = CLOUD_DATA_ROOT / user_id / "snipe" / "user.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_session(request: Request) -> CloudUser:
    """FastAPI dependency — resolves the current user from the request.

    Local mode: returns a fully-privileged "local" user pointing at SNIPE_DB.
    Cloud mode: validates X-CF-Session JWT, provisions Heimdall license,
                resolves tier, returns per-user DB paths.
    """
    if not CLOUD_MODE:
        return CloudUser(
            user_id="local",
            tier="local",
            shared_db=_LOCAL_SNIPE_DB,
            user_db=_LOCAL_SNIPE_DB,
        )

    raw_header = (
        request.headers.get("x-cf-session", "")
        or request.headers.get("cookie", "")
    )
    if not raw_header:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = _extract_session_token(raw_header)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = validate_session_jwt(token)
    _ensure_provisioned(user_id)
    tier = _fetch_cloud_tier(user_id)

    return CloudUser(
        user_id=user_id,
        tier=tier,
        shared_db=_shared_db_path(),
        user_db=_user_db_path(user_id),
    )


def require_tier(min_tier: str):
    """Dependency factory — raises 403 if the session tier is below min_tier.

    Usage: @app.post("/api/foo", dependencies=[Depends(require_tier("paid"))])
    """
    min_idx = TIERS.index(min_tier)

    def _check(session: CloudUser = Depends(get_session)) -> CloudUser:
        if session.tier == "local":
            return session  # local users always pass
        try:
            if TIERS.index(session.tier) < min_idx:
                raise HTTPException(
                    status_code=403,
                    detail=f"This feature requires {min_tier} tier or above.",
                )
        except ValueError:
            raise HTTPException(status_code=403, detail="Unknown tier.")
        return session

    return _check
