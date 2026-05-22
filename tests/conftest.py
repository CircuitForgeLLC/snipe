import os
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "postgres: mark test as requiring a live Postgres instance (SNIPE_SHARED_DB_URL must be set)",
    )


@pytest.fixture
def postgres_dsn():
    dsn = os.environ.get("SNIPE_SHARED_DB_URL")
    if not dsn:
        pytest.skip("SNIPE_SHARED_DB_URL not set — skipping Postgres tests")
    return dsn
