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


def test_ebay_adapter_accepts_protocol():
    import pathlib
    import tempfile
    from unittest.mock import MagicMock

    from app.platforms.ebay.adapter import EbayAdapter

    with tempfile.TemporaryDirectory() as tmp:
        s = Store(pathlib.Path(tmp) / "t.db")
        adapter = EbayAdapter(token_manager=MagicMock(), shared_store=s)
        assert adapter._store is s


def test_scraped_adapter_no_db_path_ref():
    import pathlib
    import tempfile

    from app.platforms.ebay.scraper import ScrapedEbayAdapter

    with tempfile.TemporaryDirectory() as tmp:
        s = Store(pathlib.Path(tmp) / "t.db")
        adapter = ScrapedEbayAdapter(shared_store=s)
        assert not hasattr(adapter, '_db_path_ref')
