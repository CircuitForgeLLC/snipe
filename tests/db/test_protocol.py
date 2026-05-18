"""Verify Store satisfies SharedTableProtocol at import time."""
from app.db.protocol import SharedTableProtocol
from app.db.store import Store


def test_store_satisfies_protocol():
    assert issubclass(Store, SharedTableProtocol)


def test_store_clone_returns_new_instance(tmp_path):
    db = tmp_path / "test.db"
    s = Store(db)
    clone = s.clone()
    assert isinstance(clone, Store)
    assert clone is not s
    assert clone._db_path == db
