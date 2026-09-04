import datetime as dt
from pathlib import Path

import pytest

from charmera_uploader.camera import PhotoFile
from charmera_uploader.config import Config
from charmera_uploader.manifest import Manifest
from charmera_uploader.pipeline import album_title_for, upload_batch


class FakePhotosClient:
    def __init__(self, fail_files: set[str] | None = None):
        self.albums_created: list[str] = []
        self.uploaded: list[tuple[Path, str]] = []
        self.fail_files = fail_files or set()

    def create_album(self, title: str) -> str:
        self.albums_created.append(title)
        return f"album-id-{title}"

    def upload_to_album(self, path: Path, album_id: str) -> str:
        if path.name in self.fail_files:
            raise RuntimeError(f"simulated failure for {path.name}")
        self.uploaded.append((path, album_id))
        return f"media-item-{path.name}"


def make_photo(tmp_path, name: str, date: dt.date) -> PhotoFile:
    p = tmp_path / name
    p.write_bytes(name.encode())
    return PhotoFile(path=p, sha256=f"hash-{name}", captured_at=date)


def test_album_title_daily_vs_single():
    cfg = Config(album_mode="daily", album_title_template="Charmera {date}")
    photo = PhotoFile(path=Path("x.jpg"), sha256="h", captured_at=dt.date(2025, 4, 2))
    assert album_title_for(cfg, photo) == "Charmera 2025-04-02"

    cfg.album_mode = "single"
    cfg.single_album_title = "Charmera Photos"
    assert album_title_for(cfg, photo) == "Charmera Photos"


def test_upload_batch_creates_one_album_per_day_and_skips_duplicates(tmp_path):
    cfg = Config(album_mode="daily")
    manifest = Manifest(tmp_path / "manifest.db")
    client = FakePhotosClient()

    day1 = dt.date(2025, 4, 2)
    photos = [
        make_photo(tmp_path, "a.jpg", day1),
        make_photo(tmp_path, "b.jpg", day1),
    ]

    result = upload_batch(photos, cfg, manifest, client)

    assert len(result.uploaded) == 2
    assert client.albums_created == ["Charmera 2025-04-02"]  # only created once, cached

    # Re-running with the same files should skip them as duplicates.
    result2 = upload_batch(photos, cfg, manifest, client)
    assert result2.uploaded == []
    assert len(result2.skipped_duplicate) == 2
    assert client.albums_created == ["Charmera 2025-04-02"]  # still just once


def test_upload_batch_records_per_file_failures_without_aborting(tmp_path):
    cfg = Config(album_mode="single")
    manifest = Manifest(tmp_path / "manifest.db")
    client = FakePhotosClient(fail_files={"bad.jpg"})

    day1 = dt.date(2025, 4, 2)
    photos = [
        make_photo(tmp_path, "good.jpg", day1),
        make_photo(tmp_path, "bad.jpg", day1),
    ]

    result = upload_batch(photos, cfg, manifest, client)

    assert [p.path.name for p in result.uploaded] == ["good.jpg"]
    assert len(result.failed) == 1
    assert result.failed[0][0].path.name == "bad.jpg"
    assert result.had_failures

    # The failed file must NOT be recorded as uploaded, so a later run can retry it.
    assert not manifest.already_uploaded("hash-bad.jpg")
    assert manifest.already_uploaded("hash-good.jpg")
