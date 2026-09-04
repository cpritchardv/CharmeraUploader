"""Ties together manifest + album selection + upload for one batch of photos."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Protocol

from .camera import PhotoFile
from .config import Config
from .manifest import Manifest

logger = logging.getLogger(__name__)


class PhotosClient(Protocol):
    """Whatever uploads photos - currently RclonePhotosClient (see rclone_photos.py)."""

    def create_album(self, title: str) -> str: ...
    def upload_to_album(self, path: Path, album_id: str) -> str: ...


@dataclasses.dataclass
class BatchResult:
    uploaded: list[PhotoFile] = dataclasses.field(default_factory=list)
    skipped_duplicate: list[PhotoFile] = dataclasses.field(default_factory=list)
    failed: list[tuple[PhotoFile, str]] = dataclasses.field(default_factory=list)

    @property
    def had_failures(self) -> bool:
        return bool(self.failed)


def album_title_for(cfg: Config, photo: PhotoFile) -> str:
    if cfg.album_mode == "single":
        return cfg.single_album_title
    return cfg.album_title_template.format(date=photo.captured_at.isoformat())


def get_or_create_album(manifest: Manifest, client: PhotosClient, title: str) -> str:
    album_id = manifest.get_album_id(title)
    if album_id is not None:
        return album_id
    album_id = client.create_album(title)
    manifest.record_album(title, album_id)
    return album_id


def upload_batch(
    photos: list[PhotoFile],
    cfg: Config,
    manifest: Manifest,
    client: PhotosClient,
) -> BatchResult:
    result = BatchResult()

    for photo in photos:
        if manifest.already_uploaded(photo.sha256):
            logger.info("Skipping already-uploaded %s", photo.path.name)
            result.skipped_duplicate.append(photo)
            continue

        try:
            title = album_title_for(cfg, photo)
            album_id = get_or_create_album(manifest, client, title)
            client.upload_to_album(photo.path, album_id)
            manifest.record_upload(photo.sha256, photo.path.name, album_id)
            result.uploaded.append(photo)
            logger.info("Uploaded %s -> album %r", photo.path.name, title)
        except Exception as exc:  # keep going on a per-file failure
            logger.exception("Failed to upload %s", photo.path)
            result.failed.append((photo, str(exc)))

    return result
