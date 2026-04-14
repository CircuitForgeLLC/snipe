import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.platforms.ebay.auth import EbayTokenManager


def test_fetches_token_on_first_call():
    manager = EbayTokenManager(client_id="id", client_secret="secret", env="sandbox")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 7200}
    mock_resp.raise_for_status = MagicMock()
    with patch("app.platforms.ebay.auth.requests.post", return_value=mock_resp) as mock_post:
        token = manager.get_token()
    assert token == "tok123"
    assert mock_post.called


def test_returns_cached_token_before_expiry():
    manager = EbayTokenManager(client_id="id", client_secret="secret", env="sandbox")
    manager._token = "cached"
    manager._expires_at = time.time() + 3600
    with patch("app.platforms.ebay.auth.requests.post") as mock_post:
        token = manager.get_token()
    assert token == "cached"
    assert not mock_post.called


def test_refreshes_token_after_expiry():
    manager = EbayTokenManager(client_id="id", client_secret="secret", env="sandbox")
    manager._token = "old"
    manager._expires_at = time.time() - 1  # expired
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "new_tok", "expires_in": 7200}
    mock_resp.raise_for_status = MagicMock()
    with patch("app.platforms.ebay.auth.requests.post", return_value=mock_resp):
        token = manager.get_token()
    assert token == "new_tok"


def test_token_fetch_failure_raises():
    """Spec requires: on token fetch failure, raise immediately — no silent fallback."""
    manager = EbayTokenManager(client_id="id", client_secret="secret", env="sandbox")
    with patch("app.platforms.ebay.auth.requests.post", side_effect=requests.RequestException("network error")):
        with pytest.raises(requests.RequestException):
            manager.get_token()
