#!/usr/bin/env python3
"""One-time Google Photos auth setup.

Run this on a computer that has a web browser - NOT on the headless Pi.
It walks you through Google's OAuth consent screen and writes out a
token.json containing a refresh token. Copy that file to the Pi (to the
path referenced by `token_path` in config.yaml, e.g. via scp) and the
daemon will use it from then on, refreshing it automatically as needed.

Prerequisites:
  1. In Google Cloud Console, create a project (or use an existing one).
  2. Enable the "Google Photos Library API".
  3. Create OAuth 2.0 credentials of type "Desktop app".
  4. Download the client secret JSON and pass its path with --client-secret.

Usage:
  python scripts/setup_google_auth.py --client-secret client_secret.json --out token.json
"""

from __future__ import annotations

import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secret", required=True, help="Path to the OAuth client secret JSON")
    parser.add_argument("--out", default="token.json", help="Where to write the resulting token")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())

    print(f"Wrote {args.out}. Copy this file to the Pi, e.g.:")
    print(f"  scp {args.out} pi@charmera-uploader.local:/etc/charmera-uploader/token.json")


if __name__ == "__main__":
    main()
