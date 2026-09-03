"""Mounting the camera's USB storage and finding photos on it."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PhotoFile:
    path: Path
    sha256: str
    captured_at: dt.date


def sha256_of(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _exif_capture_date(path: Path) -> dt.date | None:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:  # pragma: no cover
        return None

    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ("DateTimeOriginal", "DateTime"):
                    # EXIF format: "YYYY:MM:DD HH:MM:SS"
                    return dt.datetime.strptime(value, "%Y:%m:%d %H:%M:%S").date()
    except Exception:
        logger.debug("Could not read EXIF from %s", path, exc_info=True)
    return None


def capture_date_of(path: Path) -> dt.date:
    exif_date = _exif_capture_date(path)
    if exif_date is not None:
        return exif_date
    return dt.date.fromtimestamp(path.stat().st_mtime)


def find_photos(mount_point: Path, dcim_subpath: str, extensions: list[str]) -> list[PhotoFile]:
    """Recursively finds media files under the mounted volume.

    The Charmera puts stills under DCIM/ and videos under a separate
    top-level VIDEO/ folder (they're siblings, not nested), so by default
    (dcim_subpath == "") this scans the whole volume rather than just one
    subfolder. Set dcim_subpath to restrict the search to a single
    subfolder instead.
    """
    search_root = mount_point / dcim_subpath if dcim_subpath else mount_point
    if not search_root.is_dir():
        search_root = mount_point  # fall back to scanning the whole volume

    exts = {e.lower() for e in extensions}
    results: list[PhotoFile] = []
    for path in sorted(search_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        results.append(
            PhotoFile(
                path=path,
                sha256=sha256_of(path),
                captured_at=capture_date_of(path),
            )
        )
    return results


class MountError(RuntimeError):
    pass


def mount_device(device_node: str, mount_point: Path, read_write: bool) -> None:
    mount_point.mkdir(parents=True, exist_ok=True)
    mode = "rw" if read_write else "ro"
    cmd = ["mount", "-o", f"{mode},uid=0,gid=0,fmask=133,dmask=022", device_node, str(mount_point)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # fmask/dmask are only valid for FAT-like filesystems; retry without
        # them for anything else (exfat-fuse, ext, etc).
        cmd = ["mount", "-o", mode, device_node, str(mount_point)]
        result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MountError(f"mount {device_node} failed: {result.stderr.strip()}")


def unmount_device(mount_point: Path) -> None:
    result = subprocess.run(["umount", str(mount_point)], capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("umount %s failed: %s", mount_point, result.stderr.strip())
    try:
        mount_point.rmdir()
    except OSError:
        pass
