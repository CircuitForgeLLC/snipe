"""Tests for PATCH /api/preferences display.currency validation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """TestClient with a patched local DB path.

    api.cloud_session._LOCAL_SNIPE_DB is set at module import time, so we
    cannot rely on setting SNIPE_DB before import when other tests have already
    triggered the module load.  Patch the module-level variable directly so
    the session dependency points at our fresh tmp DB for the duration of this
    fixture.
    """
    db_path = tmp_path / "snipe.db"
    # Ensure the DB is initialised so the Store can create its tables.
    from circuitforge_core.db import get_connection, run_migrations

    import api.cloud_session as _cs
    conn = get_connection(db_path)
    run_migrations(conn, Path("app/db/migrations"))
    conn.close()

    from api.main import app
    with patch.object(_cs, "_LOCAL_SNIPE_DB", db_path):
        yield TestClient(app, raise_server_exceptions=False)


def test_set_display_currency_valid(client):
    """Accepted ISO 4217 codes are stored and returned."""
    for code in ("USD", "GBP", "EUR", "CAD", "AUD", "JPY", "CHF", "MXN", "BRL", "INR"):
        resp = client.patch("/api/preferences", json={"path": "display.currency", "value": code})
        assert resp.status_code == 200, f"Expected 200 for {code}, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("display", {}).get("currency") == code


def test_set_display_currency_normalises_lowercase(client):
    """Lowercase code is accepted and normalised to uppercase."""
    resp = client.patch("/api/preferences", json={"path": "display.currency", "value": "eur"})
    assert resp.status_code == 200
    assert resp.json()["display"]["currency"] == "EUR"


def test_set_display_currency_unsupported_returns_400(client):
    """Unsupported currency code returns 400 with a clear message."""
    resp = client.patch("/api/preferences", json={"path": "display.currency", "value": "XYZ"})
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "XYZ" in detail
    assert "Supported" in detail or "supported" in detail


def test_set_display_currency_empty_string_returns_400(client):
    """Empty string is not a valid currency code."""
    resp = client.patch("/api/preferences", json={"path": "display.currency", "value": ""})
    assert resp.status_code == 400


def test_set_display_currency_none_returns_400(client):
    """None is not a valid currency code."""
    resp = client.patch("/api/preferences", json={"path": "display.currency", "value": None})
    assert resp.status_code == 400


def test_other_preference_paths_unaffected(client):
    """Unrelated preference paths still work normally after currency validation added."""
    resp = client.patch("/api/preferences", json={"path": "affiliate.opt_out", "value": True})
    assert resp.status_code == 200
    assert resp.json().get("affiliate", {}).get("opt_out") is True
