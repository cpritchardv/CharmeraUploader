import datetime as dt

from charmera_uploader.camera import find_photos, sha256_of


def test_find_photos_filters_by_extension_and_hashes(tmp_path):
    dcim = tmp_path / "DCIM"
    dcim.mkdir()
    (dcim / "IMG_0001.JPG").write_bytes(b"fake jpeg bytes")
    (dcim / "IMG_0002.mp4").write_bytes(b"fake video bytes")
    (dcim / "notes.txt").write_bytes(b"not a photo")

    photos = find_photos(tmp_path, "DCIM", [".jpg", ".jpeg", ".mp4"])

    names = sorted(p.path.name for p in photos)
    assert names == ["IMG_0001.JPG", "IMG_0002.mp4"]

    expected_hash = sha256_of(dcim / "IMG_0001.JPG")
    jpg = next(p for p in photos if p.path.name == "IMG_0001.JPG")
    assert jpg.sha256 == expected_hash
    assert isinstance(jpg.captured_at, dt.date)


def test_find_photos_falls_back_to_volume_root_when_no_dcim(tmp_path):
    (tmp_path / "PIC001.png").write_bytes(b"fake png")

    photos = find_photos(tmp_path, "DCIM", [".png"])

    assert [p.path.name for p in photos] == ["PIC001.png"]


def test_find_photos_default_scan_covers_sibling_dcim_and_video_folders(tmp_path):
    # This is the real Charmera layout: stills under DCIM/, videos under a
    # separate sibling VIDEO/ folder - not nested under DCIM.
    (tmp_path / "DCIM").mkdir()
    (tmp_path / "DCIM" / "IMG_0001.JPG").write_bytes(b"fake jpeg")
    (tmp_path / "VIDEO").mkdir()
    (tmp_path / "VIDEO" / "CLIP_0001.AVI").write_bytes(b"fake avi")

    photos = find_photos(tmp_path, "", [".jpg", ".avi"])

    names = sorted(p.path.name for p in photos)
    assert names == ["CLIP_0001.AVI", "IMG_0001.JPG"]
