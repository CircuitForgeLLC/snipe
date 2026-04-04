from app.tiers import can_use, FEATURES, LOCAL_VISION_UNLOCKABLE


def test_metadata_scoring_is_free():
    assert can_use("metadata_trust_scoring", tier="free") is True


def test_photo_analysis_is_paid():
    assert can_use("photo_analysis", tier="free") is False
    assert can_use("photo_analysis", tier="paid") is True


def test_local_vision_unlocks_photo_analysis():
    assert can_use("photo_analysis", tier="free", has_local_vision=True) is True


def test_byok_does_not_unlock_photo_analysis():
    assert can_use("photo_analysis", tier="free", has_byok=True) is False


def test_saved_searches_are_free():
    # Ungated: retention feature — friction cost outweighs gate value (see tiers.py)
    assert can_use("saved_searches", tier="free") is True
    assert can_use("saved_searches", tier="paid") is True
