"""eBay Marketplace Account Deletion webhook.

Required to activate eBay production API credentials.

Protocol (https://developer.ebay.com/develop/guides-v2/marketplace-user-account-deletion):

  GET  /api/ebay/account-deletion?challenge_code=<hex>
       → {"challengeResponse": SHA256(code + token + endpoint_url)}

  POST /api/ebay/account-deletion
       Header: X-EBAY-SIGNATURE: <base64-JSON {"kid": "...", "signature": "<b64>"}>
       Body: JSON notification payload
       → 200 on valid + deleted, 412 on bad signature

Public keys are fetched from the eBay Notification API and cached for 1 hour.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import APIRouter, Header, HTTPException, Request

from app.db.store import Store
from app.platforms.ebay.auth import EbayTokenManager

log = logging.getLogger(__name__)

router = APIRouter()

_DB_PATH = Path(os.environ.get("SNIPE_DB", "data/snipe.db"))

# ── App-level token manager ───────────────────────────────────────────────────
# Lazily initialized from env vars; shared across all webhook requests.
# The Notification public_key endpoint requires a Bearer app token.
_app_token_manager: EbayTokenManager | None = None


def _get_app_token() -> str | None:
    """Return a valid eBay app-level Bearer token, or None if creds are absent."""
    global _app_token_manager
    client_id = (os.environ.get("EBAY_APP_ID") or os.environ.get("EBAY_CLIENT_ID", "")).strip()
    client_secret = (os.environ.get("EBAY_CERT_ID") or os.environ.get("EBAY_CLIENT_SECRET", "")).strip()
    if not client_id or not client_secret:
        return None
    if _app_token_manager is None:
        _app_token_manager = EbayTokenManager(client_id, client_secret)
    return _app_token_manager.get_token()


# ── Public-key cache ──────────────────────────────────────────────────────────
# eBay key rotation is rare; 1-hour TTL is appropriate.
_KEY_CACHE_TTL = 3600
_key_cache: dict[str, tuple[bytes, float]] = {}  # kid → (pem_bytes, expiry)

# The eBay Notification service is a unified production-side system — signing keys
# always live at api.ebay.com regardless of whether the app uses sandbox or production
# Browse API credentials.
_EBAY_KEY_URL = "https://api.ebay.com/commerce/notification/v1/public_key/{kid}"


def _fetch_public_key(kid: str) -> bytes:
    """Return PEM public key bytes for the given kid, using a 1-hour cache."""
    cached = _key_cache.get(kid)
    if cached and time.time() < cached[1]:
        return cached[0]

    key_url = _EBAY_KEY_URL.format(kid=kid)
    headers: dict[str, str] = {}
    app_token = _get_app_token()
    if app_token:
        headers["Authorization"] = f"Bearer {app_token}"
    else:
        log.warning("public_key fetch: no app credentials — request will likely fail")

    resp = requests.get(key_url, headers=headers, timeout=10)
    if not resp.ok:
        log.error("public key fetch failed: %s %s — body: %s", resp.status_code, key_url, resp.text[:500])
    resp.raise_for_status()
    pem_str: str = resp.json()["key"]
    pem_bytes = pem_str.encode()
    _key_cache[kid] = (pem_bytes, time.time() + _KEY_CACHE_TTL)
    return pem_bytes


# ── GET — webhook health check ───────────────────────────────────────────────

@router.get("/api/ebay/webhook-health")
def ebay_webhook_health() -> dict:
    """Lightweight health check for eBay webhook compliance monitoring.

    Returns 200 + status dict when the webhook is fully configured.
    Returns 500 when required env vars are missing.
    Intended for Uptime Kuma or similar uptime monitors.
    """
    token = os.environ.get("EBAY_NOTIFICATION_TOKEN", "")
    endpoint = os.environ.get("EBAY_NOTIFICATION_ENDPOINT", "")
    client_id = (os.environ.get("EBAY_APP_ID") or os.environ.get("EBAY_CLIENT_ID", "")).strip()
    client_secret = (os.environ.get("EBAY_CERT_ID") or os.environ.get("EBAY_CLIENT_SECRET", "")).strip()

    missing = [
        name for name, val in [
            ("EBAY_NOTIFICATION_TOKEN", token),
            ("EBAY_NOTIFICATION_ENDPOINT", endpoint),
            ("EBAY_APP_ID / EBAY_CLIENT_ID", client_id),
            ("EBAY_CERT_ID / EBAY_CLIENT_SECRET", client_secret),
        ] if not val
    ]
    if missing:
        log.error("ebay_webhook_health: missing config: %s", missing)
        raise HTTPException(
            status_code=500,
            detail=f"Webhook misconfigured — missing: {missing}",
        )
    return {
        "status": "ok",
        "endpoint": endpoint,
        "signature_verification": os.environ.get("EBAY_WEBHOOK_VERIFY_SIGNATURES", "true"),
    }


# ── GET — challenge verification ──────────────────────────────────────────────

@router.get("/api/ebay/account-deletion")
def ebay_challenge(challenge_code: str):
    """Respond to eBay's endpoint verification challenge.

    eBay sends this GET once when you register the endpoint URL.
    Response must be the SHA-256 hex digest of (code + token + endpoint).
    """
    token = os.environ.get("EBAY_NOTIFICATION_TOKEN", "")
    endpoint = os.environ.get("EBAY_NOTIFICATION_ENDPOINT", "")
    if not token or not endpoint:
        log.error("EBAY_NOTIFICATION_TOKEN or EBAY_NOTIFICATION_ENDPOINT not set")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    digest = hashlib.sha256(
        (challenge_code + token + endpoint).encode()
    ).hexdigest()
    return {"challengeResponse": digest}


# ── POST — deletion notification ──────────────────────────────────────────────

@router.post("/api/ebay/account-deletion", status_code=200)
async def ebay_account_deletion(
    request: Request,
    x_ebay_signature: Optional[str] = Header(default=None),
):
    """Process an eBay Marketplace Account Deletion notification.

    Verifies the ECDSA/SHA1 signature, then permanently deletes all stored
    data (sellers + listings) for the named eBay user.
    """
    body_bytes = await request.body()

    # 1. Parse and verify signature header
    if not x_ebay_signature:
        log.warning("ebay_account_deletion: missing X-EBAY-SIGNATURE header")
        raise HTTPException(status_code=412, detail="Missing signature")

    try:
        sig_json = json.loads(base64.b64decode(x_ebay_signature))
        kid: str = sig_json["kid"]
        sig_b64: str = sig_json["signature"]
        sig_bytes = base64.b64decode(sig_b64)
    except Exception as exc:
        log.warning("ebay_account_deletion: malformed signature header — %s", exc)
        raise HTTPException(status_code=412, detail="Malformed signature header")

    # 2. Fetch and verify with eBay public key
    # EBAY_WEBHOOK_VERIFY_SIGNATURES=false skips ECDSA during sandbox/registration phase.
    # Set to true (default) once production credentials are active.
    skip_verify = os.environ.get("EBAY_WEBHOOK_VERIFY_SIGNATURES", "true").lower() == "false"
    if skip_verify:
        log.warning("ebay_account_deletion: signature verification DISABLED — enable before production")
    else:
        try:
            pem_bytes = _fetch_public_key(kid)
            pub_key = load_pem_public_key(pem_bytes)
            pub_key.verify(sig_bytes, body_bytes, ECDSA(SHA1()))
        except InvalidSignature:
            log.warning("ebay_account_deletion: ECDSA signature verification failed (kid=%s)", kid)
            raise HTTPException(status_code=412, detail="Signature verification failed")
        except Exception as exc:
            log.error("ebay_account_deletion: unexpected error during verification — %s", exc)
            raise HTTPException(status_code=412, detail="Verification error")

    # 3. Extract username from notification payload and delete data
    try:
        payload = json.loads(body_bytes)
        username: str = payload["notification"]["data"]["username"]
    except (KeyError, json.JSONDecodeError) as exc:
        log.error("ebay_account_deletion: could not parse payload — %s", exc)
        raise HTTPException(status_code=400, detail="Unrecognisable payload")

    store = Store(_DB_PATH)
    store.delete_seller_data("ebay", username)
    log.info("ebay_account_deletion: deleted data for eBay user %r", username)
    return {}
