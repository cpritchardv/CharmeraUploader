"""Uploads to Google Photos via an rclone remote.

This deliberately does not talk to the Google Photos API directly. Doing
that requires registering your own OAuth app in Google Cloud Console,
which - for this specific API - means either re-authorizing every 7 days
(Testing status) or completing full app Branding (homepage, privacy
policy, terms of service) and publishing before Google will treat it as
more than a throwaway test app. rclone ships its own already
Google-verified OAuth client for exactly this use case, so setup is just
`rclone config` and a normal "Sign in with Google" - no Cloud Console
project of your own required. See README.md for the one-time setup.

rclone's Google Photos backend has no separate "album ID" concept the way
the raw API does - albums are addressed by title as a path segment
(`remote:album/<title>/`), so the "album_id" this module hands back to
the pipeline/manifest is just that title string, unchanged.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class RclonePhotosError(RuntimeError):
    pass


class RclonePhotosClient:
    def __init__(self, remote: str):
        self.remote = remote

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        cmd = ["rclone", *args]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result

    def create_album(self, title: str) -> str:
        result = self._run(["mkdir", f"{self.remote}:album/{title}"])
        if result.returncode != 0:
            raise RclonePhotosError(f"rclone mkdir for album {title!r} failed: {result.stderr.strip()}")
        logger.info("Created (or confirmed) Google Photos album %r via rclone", title)
        return title

    def upload_to_album(self, path: Path, album_id: str) -> str:
        """Uploads one file into the album. album_id is the album title (see module docstring)."""
        destination = f"{self.remote}:album/{album_id}/"
        result = self._run(["copy", str(path), destination])
        if result.returncode != 0:
            raise RclonePhotosError(f"rclone copy {path} -> {destination} failed: {result.stderr.strip()}")
        return path.name
