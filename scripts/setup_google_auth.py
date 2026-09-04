#!/usr/bin/env python3
"""One-time Google Photos auth setup, over an SSH tunnel.

Two things this script does NOT use, because they don't work for this API:

  - Device flow (the short-code approach): Google's own API rejects
    Google Photos scopes there with "invalid_scope" - confirmed by
    actually calling it, not assumed.
  - A LAN IP address as the redirect target: Google's OAuth clients
    reject raw IP addresses as redirect URI hosts - only "localhost" is
    allowed over plain HTTP.

So this uses the one thing that does work for a browser-less server
reached only over SSH: an SSH *local port forward*, so a browser on your
own computer completes a normal Google sign-in that redirects to
"localhost", which SSH quietly tunnels through to this script running on
the Pi. No code to copy or paste - the browser does the whole thing.

How to run it:

  1. Log into the Pi with a port forward added to your normal ssh command:

         ssh -L 8765:localhost:8765 root@<pi-ip-or-hostname>

     (8765 matches this script's default --port - add -L to whatever ssh
     command you already use, it doesn't replace anything else about how
     you log in.)

  2. In that same SSH session, run this script:

         venv/bin/python scripts/setup_google_auth.py \\
             --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET \\
             --out /etc/charmera-uploader/token.json

  3. It prints a Google sign-in URL. Open it in a browser on the SAME
     computer you ran that ssh -L command from (not your phone - the
     tunnel only exists on that one machine). Sign in and approve.

  4. The browser redirects to "localhost:8765", invisibly forwarded over
     SSH back to this script, which captures it automatically and writes
     token.json. The script exits on its own once that happens.

Prerequisites (from any browser, done once, before step 1):
  1. In Google Cloud Console, create a project (or use an existing one)
     and enable the "Google Photos Library API".
  2. Create OAuth 2.0 credentials of type "Web application" (not
     "Desktop app" or "TVs and Limited Input devices" - those don't
     support this flow for this API).
  3. Under "Authorized redirect URIs", add exactly:

         http://localhost:8765/

     (matching --port below if you change it from the default 8765).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - required name from BaseHTTPRequestHandler
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
            body = b"<html><body>Authorized - you can close this tab.</body></html>"
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
            body = f"<html><body>Authorization failed: {_CallbackHandler.error}</body></html>".encode()
        else:
            # Some other request (e.g. the browser's favicon.ico probe) -
            # ignore it and keep waiting for the real callback.
            body = b"<html><body>Waiting for authorization...</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass  # keep stdout clean; the script prints its own status lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--client-id", required=True, help="OAuth client ID (Web application type)")
    parser.add_argument("--client-secret", required=True, help="OAuth client secret for that client")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Must match both your `ssh -L` forward and the redirect URI registered in Console",
    )
    parser.add_argument("--out", default="token.json", help="Where to write the resulting token")
    args = parser.parse_args()

    redirect_uri = f"http://localhost:{args.port}/"
    server = HTTPServer(("127.0.0.1", args.port), _CallbackHandler)

    query = urllib.parse.urlencode(
        {
            "client_id": args.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    auth_url = f"{AUTH_URL}?{query}"

    print()
    print("=" * 60)
    print("Open this URL in a browser on the SAME computer as your")
    print("`ssh -L` tunnel (not your phone):")
    print()
    print(auth_url)
    print("=" * 60)
    print()
    print("Waiting for you to approve...")

    while _CallbackHandler.code is None and _CallbackHandler.error is None:
        server.handle_request()  # blocks for exactly one HTTP request, then returns

    if _CallbackHandler.error:
        print(f"Authorization failed: {_CallbackHandler.error}", file=sys.stderr)
        sys.exit(1)

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "code": _CallbackHandler.code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if not token_resp.ok:
        print(f"Token exchange failed: {token_resp.status_code} {token_resp.text}", file=sys.stderr)
        sys.exit(1)

    payload = token_resp.json()
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


if __name__ == "__main__":
    main()
