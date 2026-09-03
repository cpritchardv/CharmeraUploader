"""Local dedupe/state store.

Google's Photos API (as of the 2025 API changes) only grants write access
via the `photoslibrary.appendonly` scope: an app can create albums and add
media to them, but it cannot list what's already in the library. So all
"have I already uploaded this?" and "which album ID did I already create for
today?" bookkeeping has to live locally, next to the uploader itself.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class Manifest:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    sha256 TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    album_id TEXT,
                    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS albums (
                    title TEXT PRIMARY KEY,
                    album_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    def already_uploaded(self, sha256: str) -> bool:
        with closing(self._conn.execute(
            "SELECT 1 FROM uploads WHERE sha256 = ?", (sha256,)
        )) as cur:
            return cur.fetchone() is not None

    def record_upload(self, sha256: str, filename: str, album_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO uploads (sha256, filename, album_id) VALUES (?, ?, ?)",
                (sha256, filename, album_id),
            )

    def get_album_id(self, title: str) -> str | None:
        with closing(self._conn.execute(
            "SELECT album_id FROM albums WHERE title = ?", (title,)
        )) as cur:
            row = cur.fetchone()
            return row[0] if row else None

    def record_album(self, title: str, album_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO albums (title, album_id) VALUES (?, ?)",
                (title, album_id),
            )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Manifest":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
