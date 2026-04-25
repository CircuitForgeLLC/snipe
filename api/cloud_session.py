"""Cloud session resolution for Snipe FastAPI.

Delegates JWT validation, Heimdall provisioning, tier resolution, and guest
session management to circuitforge_core.CloudSessionFactory. Snipe-specific
CloudUser (shared_db + user_db paths), SessionFeatures, and DB helpers are
kept here.

FastAPI usage:
    @app.get("/api/search")
    def search(session: CloudUser = Depends(get_session)):
        shared_store = Store(session.shared_db)
        user_store   = Store(session.user_db)
        ...
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from circuitforge_core.cloud_session import CloudSessionFactory as _CoreFactory
from fastapi import Depends, HTTPException, Request, Response

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CLOUD_MODE: bool = os.environ.get("CLOUD_MODE", "").lower() in ("1", "true", "yes")
CLOUD_DATA_ROOT: Path = Path(os.environ.get("CLOUD_DATA_ROOT", "/devl/snipe-cloud-data"))

_LOCAL_SNIPE_DB: Path = Path(os.environ.get("SNIPE_DB", "data/snipe.db"))

TIERS = ["free", "paid", "premium", "ultra"]

_core = _CoreFactory(product="snipe")


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
    llm_query_builder: bool


def compute_features(tier: str) -> SessionFeatures:
    """Compute feature flags from tier. Evaluated server-side; sent to frontend."""
    local = tier == "local"
    paid_plus = local or tier in ("paid", "premium", "ultra")

    return SessionFeatures(
        saved_searches=True,  # all tiers get saved searches
        saved_searches_limit=None if paid_plus else 3,
        background_monitoring=paid_plus,
        max_pages=999 if local else (5 if paid_plus else 1),
        upc_search=paid_plus,
        photo_analysis=paid_plus,
        shared_scammer_db=paid_plus,
        shared_image_db=paid_plus,
        llm_query_builder=paid_plus,
    )


# ── DB path helpers ───────────────────────────────────────────────────────────

def _shared_db_path() -> Path:
    path = CLOUD_DATA_ROOT / "shared" / "shared.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _user_db_path(user_id: str) -> Path:
    path = CLOUD_DATA_ROOT / user_id / "snipe" / "user.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _anon_db_path() -> Path:
    """Shared pool DB for unauthenticated visitors.

    All anonymous searches write listing data here. Seller and market comp
    data accumulates in shared_db as normal, growing the anti-scammer corpus
    with every public search regardless of auth state.
    """
    path = CLOUD_DATA_ROOT / "anonymous" / "snipe" / "user.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_session(request: Request, response: Response) -> CloudUser:
    """FastAPI dependency — resolves the current user from the request.

    Delegates auth/tier resolution to cf-core CloudSessionFactory, then maps
    the result to Snipe's CloudUser with shared_db + user_db paths.

    Local mode: fully-privileged "local" user pointing at SNIPE_DB.
    Cloud mode: validates X-CF-Session JWT, provisions Heimdall license,
                resolves tier, returns per-user DB paths.
    Anonymous: guest session with free-tier access to shared scammer corpus.
    """
    core_user = _core.resolve(request, response)
    uid, tier = core_user.user_id, core_user.tier

    if not CLOUD_MODE or uid in ("local", "local-dev"):
        return CloudUser(user_id=uid, tier=tier, shared_db=_LOCAL_SNIPE_DB, user_db=_LOCAL_SNIPE_DB)
    if uid.startswith("anon-"):
        return CloudUser(user_id=uid, tier=tier, shared_db=_shared_db_path(), user_db=_anon_db_path())
    return CloudUser(user_id=uid, tier=tier, shared_db=_shared_db_path(), user_db=_user_db_path(uid))


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
