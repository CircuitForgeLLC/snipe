"""eBay OAuth2 client credentials token manager."""
from __future__ import annotations
import base64
import time
from typing import Optional
import requests

EBAY_OAUTH_URLS = {
    "production": "https://api.ebay.com/identity/v1/oauth2/token",
    "sandbox":    "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
}


class EbayTokenManager:
    """Fetches and caches eBay app-level OAuth tokens. Thread-safe for single process."""

    def __init__(self, client_id: str, client_secret: str, env: str = "production"):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = EBAY_OAUTH_URLS[env]
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    @property
    def client_id(self) -> str:
        return self._client_id

    def get_token(self) -> str:
        """Return a valid access token, fetching or refreshing as needed."""
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        self._fetch_token()
        return self._token  # type: ignore[return-value]

    def _fetch_token(self) -> None:
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = requests.post(
            self._token_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
