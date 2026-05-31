#!/usr/bin/env python3
"""
One-time helper to obtain a Spotify REFRESH TOKEN for the now-playing card.

Run locally (never in CI):

    export SPOTIFY_CLIENT_ID=xxxx
    export SPOTIFY_CLIENT_SECRET=xxxx
    python3 scripts/spotify_auth.py

Prereqs in your Spotify app (https://developer.spotify.com/dashboard):
  - Add Redirect URI EXACTLY:  http://127.0.0.1:8888/callback

The script opens your browser, you approve, and it prints SPOTIFY_REFRESH_TOKEN.
Add that (plus client id/secret) as repo Actions secrets. It also generates the
first assets/spotify.svg right away so you can see it immediately.
"""
import base64
import json
import os
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

CID = os.environ.get("SPOTIFY_CLIENT_ID")
CSECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-currently-playing user-read-recently-played"
_code = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        q = urllib.parse.urlparse(self.path)
        if q.path != "/callback":
            self.send_response(404); self.end_headers(); return
        params = urllib.parse.parse_qs(q.query)
        _code["code"] = params.get("code", [None])[0]
        _code["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html"); self.end_headers()
        msg = "✅ Authorized! You can close this tab and return to the terminal."
        if _code.get("error"):
            msg = f"❌ Error: {_code['error']}"
        self.wfile.write(f"<html><body style='font-family:sans-serif;background:#0d1117;color:#1db954;text-align:center;padding-top:80px'><h2>{msg}</h2></body></html>".encode())

    def log_message(self, *a):  # silence
        pass


def main():
    if not (CID and CSECRET):
        raise SystemExit("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET first.")
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": CID, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": SCOPES})
    srv = HTTPServer(("127.0.0.1", 8888), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    print("Opening browser to authorize... if it doesn't open, visit:\n", auth_url)
    webbrowser.open(auth_url)
    # wait for the single callback
    while "code" not in _code and "error" not in _code:
        pass
    if _code.get("error") or not _code.get("code"):
        raise SystemExit(f"Authorization failed: {_code.get('error')}")

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": _code["code"],
        "redirect_uri": REDIRECT}).encode()
    auth = base64.b64encode(f"{CID}:{CSECRET}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=body,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        tok = json.load(r)
    rt = tok.get("refresh_token")
    print("\n" + "=" * 60)
    print("SPOTIFY_REFRESH_TOKEN:\n" + (rt or "(none returned)"))
    print("=" * 60)
    print("\nAdd these 3 repo secrets (Settings > Secrets and variables > Actions):")
    print("  SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN")

    # generate the first card immediately
    if rt:
        os.environ["SPOTIFY_REFRESH_TOKEN"] = rt
        try:
            import spotify_card  # same dir when run from scripts/
            spotify_card.RTOKEN = rt
            spotify_card.CID = CID
            spotify_card.CSECRET = CSECRET
            spotify_card.main()
            print("\nGenerated assets/spotify.svg with your live data ✨")
        except Exception as e:  # noqa: BLE001
            print("Run scripts/spotify_card.py to generate the card:", e)


if __name__ == "__main__":
    main()
