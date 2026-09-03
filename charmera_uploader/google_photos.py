"""Minimal Google Photos Library API client.

Only the `photoslibrary.appendonly` scope is used (see manifest.py for why:
that scope is write-only, so this module never tries to list or search
existing library/album content - it only creates albums and uploads media,
and relies on the local manifest to remember album IDs and what's already
been uploaded).
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
API_BASE = "https://photoslibrary.googleapis.com/v1"
UPLOAD_URL = f"{API_BASE}/uploads"
BATCH_CREATE_URL = f"{API_BASE}/mediaItems:batchCreate"
ALBUMS_URL = f"{API_BASE}/albums"

_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
}


class GooglePhotosError(RuntimeError):
    pass


class GooglePhotosClient:
    def __init__(self, token_path: str | Path):
        self.token_path = Path(token_path)
        if not self.token_path.exists():
            raise GooglePhotosError(
                f"No credentials at {self.token_path}. Run scripts/setup_google_auth.py "
                "on a machine with a browser first, then copy the resulting token.json here."
            )
        self._creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        self._session = requests.Session()

    def _ensure_fresh(self) -> None:
        if not self._creds.valid:
            self._creds.refresh(Request())
            self.token_path.write_text(self._creds.to_json())

    def _headers(self, **extra: str) -> dict:
        self._ensure_fresh()
        headers = {"Authorization": f"Bearer {self._creds.token}"}
        headers.update(extra)
        return headers

    def create_album(self, title: str) -> str:
        resp = self._session.post(
            ALBUMS_URL,
            headers=self._headers(**{"Content-type": "application/json"}),
            json={"album": {"title": title}},
            timeout=30,
        )
        if not resp.ok:
            raise GooglePhotosError(f"create_album({title!r}) failed: {resp.status_code} {resp.text}")
        album_id = resp.json()["id"]
        logger.info("Created Google Photos album %r (id=%s)", title, album_id)
        return album_id

    def _upload_bytes(self, path: Path) -> str:
        mime_type = _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        headers = self._headers(**{
            "Content-type": "application/octet-stream",
            "X-Goog-Upload-Content-Type": mime_type,
            "X-Goog-Upload-Protocol": "raw",
        })
        with path.open("rb") as fh:
            resp = self._session.post(UPLOAD_URL, headers=headers, data=fh, timeout=120)
        if not resp.ok:
            raise GooglePhotosError(f"upload {path} failed: {resp.status_code} {resp.text}")
        return resp.text  # the raw upload token

    def upload_to_album(self, path: Path, album_id: str) -> str:
        """Uploads one file and adds it to an album. Returns the new mediaItem ID."""
        upload_token = self._upload_bytes(path)
        resp = self._session.post(
            BATCH_CREATE_URL,
            headers=self._headers(**{"Content-type": "application/json"}),
            json={
                "albumId": album_id,
                "newMediaItems": [
                    {
                        "description": path.name,
                        "simpleMediaItem": {"uploadToken": upload_token},
                    }
                ],
            },
            timeout=60,
        )
        if not resp.ok:
            raise GooglePhotosError(f"batchCreate for {path} failed: {resp.status_code} {resp.text}")

        body = resp.json()
        results = body.get("newMediaItemResults", [])
        if not results:
            raise GooglePhotosError(f"batchCreate for {path} returned no results: {body}")

        result = results[0]
        status = result.get("status", {})
        # Google uses gRPC-style status codes; 0 (or absent) means OK.
        if status.get("code") not in (None, 0):
            raise GooglePhotosError(f"batchCreate for {path} failed: {status}")

        return result["mediaItem"]["id"]
