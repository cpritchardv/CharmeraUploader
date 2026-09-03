from charmera_uploader.manifest import Manifest


def test_dedupe_roundtrip(tmp_path):
    m = Manifest(tmp_path / "manifest.db")
    assert not m.already_uploaded("abc123")

    m.record_upload("abc123", "photo.jpg", "album-1")
    assert m.already_uploaded("abc123")
    assert not m.already_uploaded("other")


def test_album_id_cache(tmp_path):
    m = Manifest(tmp_path / "manifest.db")
    assert m.get_album_id("Charmera 2025-04-02") is None

    m.record_album("Charmera 2025-04-02", "album-xyz")
    assert m.get_album_id("Charmera 2025-04-02") == "album-xyz"


def test_persists_across_instances(tmp_path):
    db = tmp_path / "manifest.db"
    Manifest(db).record_upload("hash1", "a.jpg", "album-1")

    m2 = Manifest(db)
    assert m2.already_uploaded("hash1")
