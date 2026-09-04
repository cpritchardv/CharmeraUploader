import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from charmera_uploader.rclone_photos import RclonePhotosClient, RclonePhotosError


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_create_album_runs_rclone_mkdir():
    client = RclonePhotosClient("googlephotos")
    with patch.object(RclonePhotosClient, "_run", return_value=_completed(0)) as run:
        album_id = client.create_album("Charmera 2025-04-02")

    run.assert_called_once_with(["mkdir", "googlephotos:album/Charmera 2025-04-02"])
    assert album_id == "Charmera 2025-04-02"


def test_create_album_raises_on_failure():
    client = RclonePhotosClient("googlephotos")
    with patch.object(RclonePhotosClient, "_run", return_value=_completed(1, "boom")):
        with pytest.raises(RclonePhotosError, match="boom"):
            client.create_album("Some Album")


def test_upload_to_album_runs_rclone_copy(tmp_path):
    photo = tmp_path / "IMG_0001.jpg"
    photo.write_bytes(b"fake jpeg")

    client = RclonePhotosClient("googlephotos")
    with patch.object(RclonePhotosClient, "_run", return_value=_completed(0)) as run:
        result = client.upload_to_album(photo, "Charmera 2025-04-02")

    run.assert_called_once_with(["copy", str(photo), "googlephotos:album/Charmera 2025-04-02/"])
    assert result == "IMG_0001.jpg"


def test_upload_to_album_raises_on_failure(tmp_path):
    photo = tmp_path / "IMG_0001.jpg"
    photo.write_bytes(b"fake jpeg")

    client = RclonePhotosClient("googlephotos")
    with patch.object(RclonePhotosClient, "_run", return_value=_completed(1, "network error")):
        with pytest.raises(RclonePhotosError, match="network error"):
            client.upload_to_album(photo, "Charmera 2025-04-02")
