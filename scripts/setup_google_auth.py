#!/usr/bin/env python3
"""One-time Google Photos auth setup, using OAuth's device flow.

Run this ON THE PI itself (inside the project's venv - it only needs the
`requests` library, already installed by install.sh). Nothing needs
installing on any other computer: you'll be given a short code and a URL,
which you open in a browser on literally any device - your phone is fine -
to approve access. Once approved, this writes token.json with a refresh
token the daemon will use from then on, refreshing it automatically.

Prerequisites (done from any browser, e.g. on your phone or laptop):
  1. In Google Cloud Console, create a project (or use an existing one).
  2. Enable the "Google Photos Library API".
  3. Create OAuth 2.0 credentials of type "TVs and Limited Input devices"
     (NOT "Desktop app" - only this client type supports the device flow
     this script uses). The client ID and client secret are shown right
     on the credentials page, no file to download.

Usage (run on the Pi):
  venv/bin/python scripts/setup_google_auth.py \
      --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET \
      --out /etc/charmera-uploader/token.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import requests

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--client-id", required=True, help="OAuth client ID (TVs and Limited Input devices type)"
    )
    parser.add_argument("--client-secret", required=True, help="OAuth client secret for that client")
    parser.add_argument("--out", default="token.json", help="Where to write the resulting token")
    args = parser.parse_args()

    resp = requests.post(
        DEVICE_CODE_URL,
        data={"client_id": args.client_id, "scope": " ".join(SCOPES)},
        timeout=30,
    )
    if not resp.ok:
        print(f"Error requesting a device code: {resp.status_code} {resp.text}", file=sys.stderr)
        print(
            "Double check --client-id is the client from an OAuth client of type "
            "'TVs and Limited Input devices' (not 'Desktop app'), copied with no "
            "extra spaces/quotes.",
            file=sys.stderr,
        )
        sys.exit(1)
    device = resp.json()

    print()
    print("=" * 60)
    print(f"1. On your phone (or any browser), open: {device['verification_url']}")
    print(f"2. Enter this code when prompted:         {device['user_code']}")
    print("=" * 60)
    print()
    print("Waiting for you to approve...")

    interval = device.get("interval", 5)
    deadline = time.time() + device.get("expires_in", 1800)

    while time.time() < deadline:
        time.sleep(interval)
        token_resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "device_code": device["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        payload = token_resp.json()

        if token_resp.ok:
            token_data = {
                "token": payload["access_token"],
                "refresh_token": payload["refresh_token"],
                "token_uri": TOKEN_URL,
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "scopes": SCOPES,
                "type": "authorized_user",
            }
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(token_data, fh)
            print(f"Success - wrote {args.out}")
            return

        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue

        print(f"Authorization failed: {payload}", file=sys.stderr)
        sys.exit(1)

    print("Timed out waiting for approval - run this again.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
