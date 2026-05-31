#!/usr/bin/env python3
"""
Generate a Spotify "Now Playing / Recently Played" card as a committed SVG.

Reliable by design: the SVG (with album art base64-embedded) is committed to the
repo and served by GitHub raw -> never depends on a third-party widget host.
Refreshed by .github/workflows/spotify.yml.

Env (set as repo secrets for CI; export locally for a one-off):
  SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN
With no/invalid creds it renders a clean "offline" card (used as the initial
placeholder) so the README image is never broken.

Output: assets/spotify.svg
"""
import base64
import json
import os
import urllib.parse
import urllib.request
from html import escape

CID = os.environ.get("SPOTIFY_CLIENT_ID")
CSECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
RTOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN")

# theme (matches the other cards, with Spotify green)
BG = "#0d1117"
BORDER = "#30363d"
GREEN = "#1db954"
TEXT = "#e6edf3"
MUTED = "#8b949e"
FONT = "'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, (r.read() if r.status != 204 else b"")


def access_token():
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": RTOKEN}).encode()
    auth = base64.b64encode(f"{CID}:{CSECRET}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=body,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["access_token"]


def fetch():
    if not (CID and CSECRET and RTOKEN):
        return {"state": "offline"}
    try:
        tok = access_token()
        h = {"Authorization": f"Bearer {tok}"}
        status, raw = _get(
            "https://api.spotify.com/v1/me/player/currently-playing", h)
        if status == 200 and raw:
            d = json.loads(raw)
            if d.get("item") and d.get("is_playing"):
                it = d["item"]
                return _track(it, "playing", progress=d.get("progress_ms"),
                              duration=it.get("duration_ms"))
        # fall back to most recent
        status, raw = _get(
            "https://api.spotify.com/v1/me/player/recently-played?limit=1", h)
        if status == 200 and raw:
            items = json.loads(raw).get("items", [])
            if items:
                return _track(items[0]["track"], "recent")
    except Exception as e:  # noqa: BLE001
        print("spotify fetch failed:", e)
    return {"state": "offline"}


def _track(it, state, progress=None, duration=None):
    imgs = (it.get("album", {}) or {}).get("images", [])
    url = imgs[-1]["url"] if imgs else None
    img_b64 = None
    if url:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                img_b64 = base64.b64encode(r.read()).decode()
        except Exception:  # noqa: BLE001
            img_b64 = None
    return {
        "state": state,
        "track": it.get("name", "Unknown"),
        "artist": ", ".join(a["name"] for a in it.get("artists", [])) or "Unknown",
        "img": img_b64,
        "progress": progress, "duration": duration,
    }


def trunc(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def bars(x, y, animate):
    out = []
    heights = [10, 16, 7, 13]
    durs = ["0.9s", "1.3s", "0.7s", "1.1s"]
    for i, (hh, du) in enumerate(zip(heights, durs)):
        bx = x + i * 6
        if animate:
            out.append(
                f'<rect x="{bx}" y="{y}" width="4" height="{hh}" rx="1" fill="{GREEN}">'
                f'<animate attributeName="height" values="4;{hh};4" dur="{du}" repeatCount="indefinite"/>'
                f'<animate attributeName="y" values="{y+hh-4};{y};{y+hh-4}" dur="{du}" repeatCount="indefinite"/>'
                f'</rect>')
        else:
            out.append(f'<rect x="{bx}" y="{y}" width="4" height="6" rx="1" fill="{MUTED}"/>')
    return "".join(out)


def render(d):
    w, h = 480, 150
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" role="img">',
        f'<rect x="0.5" y="0.5" rx="8" width="{w-1}" height="{h-1}" fill="{BG}" stroke="{BORDER}"/>',
        '<defs><clipPath id="art"><rect x="20" y="25" width="100" height="100" rx="8"/></clipPath></defs>',
    ]
    # album art / logo
    if d.get("img"):
        parts.append(
            f'<image x="20" y="25" width="100" height="100" clip-path="url(#art)" '
            f'href="data:image/jpeg;base64,{d["img"]}" preserveAspectRatio="xMidYMid slice"/>')
    else:
        parts.append(
            f'<rect x="20" y="25" width="100" height="100" rx="8" fill="#0b0e14" stroke="{BORDER}"/>'
            f'<circle cx="70" cy="75" r="26" fill="none" stroke="{GREEN}" stroke-width="3"/>'
            f'<text x="70" y="84" font-family="{FONT}" font-size="26" fill="{GREEN}" text-anchor="middle">♫</text>')

    tx = 140
    state = d["state"]
    if state == "offline":
        label, animate = "Spotify", False
        track = "Not playing right now"
        artist = "tap to see what I vibe to →"
    elif state == "playing":
        label, animate = "Now Playing", True
        track, artist = trunc(d["track"], 30), trunc(d["artist"], 36)
    else:
        label, animate = "Recently Played", True
        track, artist = trunc(d["track"], 30), trunc(d["artist"], 36)

    parts.append(bars(tx, 38, animate))
    parts.append(
        f'<text x="{tx+30}" y="50" font-family="{FONT}" font-size="13" font-weight="700" '
        f'fill="{GREEN}" letter-spacing="0.5">{escape(label.upper())}</text>')
    parts.append(
        f'<text x="{tx}" y="84" font-family="{FONT}" font-size="17" font-weight="700" '
        f'fill="{TEXT}">{escape(track)}</text>')
    parts.append(
        f'<text x="{tx}" y="106" font-family="{FONT}" font-size="13" fill="{MUTED}">{escape(artist)}</text>')

    # progress bar (playing) else accent underline
    if state == "playing" and d.get("duration"):
        frac = max(0.0, min(1.0, (d.get("progress") or 0) / d["duration"]))
        parts.append(
            f'<rect x="{tx}" y="120" width="300" height="4" rx="2" fill="{BORDER}"/>'
            f'<rect x="{tx}" y="120" width="{300*frac:.0f}" height="4" rx="2" fill="{GREEN}"/>')
    else:
        parts.append(f'<rect x="{tx}" y="120" width="300" height="3" rx="1.5" fill="{BORDER}"/>')

    parts.append("</svg>\n")
    return "".join(parts)


def main():
    d = fetch()
    os.makedirs("assets", exist_ok=True)
    open("assets/spotify.svg", "w").write(render(d))
    print(f"generated assets/spotify.svg (state={d['state']})")


if __name__ == "__main__":
    main()
