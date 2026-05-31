#!/usr/bin/env python3
"""
Generate self-hosted GitHub stat cards as static SVGs.

Why: the public github-readme-stats / github-profile-trophy instances are
frequently GitHub-rate-limited (503/402) and render as broken images. These
SVGs are committed to the repo and served by GitHub itself -> never rate-limited.
A scheduled GitHub Action (.github/workflows/stats.yml) re-runs this daily.

Output: assets/stats.svg, assets/top-langs.svg, assets/trophy.svg

Token: reads GH_TOKEN or GITHUB_TOKEN from the environment. A classic PAT with
`read:user` + `repo` makes commit counts private-inclusive; the default Actions
GITHUB_TOKEN yields public-only numbers.
"""
import json
import os
import sys
import urllib.request
from html import escape

USER = os.environ.get("GH_USER", "technitish9123")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
# Languages excluded from the "Most Used Languages" card (data/markup noise).
EXCLUDE_LANGS = {x.strip() for x in os.environ.get(
    "EXCLUDE_LANGS", "Jupyter Notebook").split(",") if x.strip()}
TOP_N = 7

# ---- tokyonight-ish theme -------------------------------------------------
BG = "#0d1117"
BORDER = "#30363d"
TITLE = "#00ced1"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
ACCENT = "#8a2be2"
RING = "#00ced1"
FONT = "'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if "errors" in out:
        raise SystemExit(f"GraphQL errors: {out['errors']}")
    return out["data"]


def fetch():
    q = """
    query($login: String!) {
      user(login: $login) {
        name
        createdAt
        followers { totalCount }
        pullRequests { totalCount }
        issues { totalCount }
        repositoriesContributedTo(contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) { totalCount }
        contributionsCollection { totalCommitContributions restrictedContributionsCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
          totalCount
          nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
        }
      }
    }"""
    u = gql(q, {"login": USER})["user"]
    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n in EXCLUDE_LANGS:
                continue
            d = langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or "#888"})
            d["size"] += e["size"]
    top = sorted(langs.items(), key=lambda x: -x[1]["size"])[:TOP_N]
    cc = u["contributionsCollection"]
    return {
        "name": u["name"] or USER,
        "created": u["createdAt"][:4],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "repos": u["repositories"]["totalCount"],
        "stars": stars,
        "top": top,
    }


def card(w, h, title, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" role="img">
  <rect x="0.5" y="0.5" rx="8" width="{w-1}" height="{h-1}" fill="{BG}" stroke="{BORDER}"/>
  <text x="25" y="35" font-family="{FONT}" font-size="18" font-weight="700" fill="{TITLE}">{escape(title)}</text>
{body}
</svg>
'''


def svg_stats(d):
    rows = [
        ("★", "Total Stars Earned", d["stars"]),
        ("◉", "Commits (last year)", d["commits"]),
        ("⇅", "Total Pull Requests", d["prs"]),
        ("⚠", "Total Issues", d["issues"]),
        ("❖", "Contributed to (last year)", d["contributed"]),
        ("☻", "Followers", d["followers"]),
    ]
    # decorative grade ring (self-computed; not a global percentile)
    score = d["stars"] * 3 + d["followers"] * 2 + d["prs"] * 0.6 + \
        d["commits"] * 0.1 + d["contributed"] * 1.5 + d["repos"] * 0.5
    for thr, g, frac in [(400, "S", .95), (250, "A+", .85), (150, "A", .72),
                         (90, "A-", .6), (50, "B+", .48), (0, "B", .38)]:
        if score >= thr:
            grade, fill = g, frac
            break
    body = []
    y = 72
    for sym, label, val in rows:
        body.append(
            f'<text x="35" y="{y}" font-family="{FONT}" font-size="15" fill="{ACCENT}">{sym}</text>'
            f'<text x="58" y="{y}" font-family="{FONT}" font-size="14" fill="{TEXT}">{escape(label)}</text>'
            f'<text x="320" y="{y}" font-family="{FONT}" font-size="14" font-weight="700" fill="{TITLE}" text-anchor="end">{val:,}</text>')
        y += 26
    # ring
    cx, cy, r = 400, 120, 42
    import math
    circ = 2 * math.pi * r
    dash = circ * fill
    body.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-width="6"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{RING}" stroke-width="6" '
        f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy+2}" font-family="{FONT}" font-size="26" font-weight="700" fill="{TITLE}" text-anchor="middle">{grade}</text>'
        f'<text x="{cx}" y="{cy+22}" font-family="{FONT}" font-size="11" fill="{MUTED}" text-anchor="middle">Grade</text>')
    return card(480, 235, f"{d['name']}'s GitHub Stats", "  " + "\n  ".join(body))


def svg_langs(d):
    total = sum(v["size"] for _, v in d["top"]) or 1
    body = ['<defs><clipPath id="bar"><rect x="25" y="55" width="430" height="10" rx="5"/></clipPath></defs>',
            '<g clip-path="url(#bar)">']
    # stacked bar (clipped to rounded ends)
    x = 25.0
    barw = 430.0
    for name, v in d["top"]:
        seg = barw * v["size"] / total
        body.append(
            f'<rect x="{x:.1f}" y="55" width="{seg:.2f}" height="10" fill="{v["color"]}"/>')
        x += seg
    body.append('</g>')
    # legend, two columns
    col_x = [35, 250]
    ly = 95
    for i, (name, v) in enumerate(d["top"]):
        cx = col_x[i % 2]
        if i % 2 == 0 and i:
            ly += 26
        pct = 100 * v["size"] / total
        body.append(
            f'<circle cx="{cx}" cy="{ly-4}" r="5" fill="{v["color"]}"/>'
            f'<text x="{cx+14}" y="{ly}" font-family="{FONT}" font-size="13" fill="{TEXT}">{escape(name)}</text>'
            f'<text x="{cx+150}" y="{ly}" font-family="{FONT}" font-size="13" fill="{MUTED}" text-anchor="end">{pct:.1f}%</text>')
    h = 95 + ((len(d["top"]) + 1) // 2) * 26 + 10
    return card(480, h, "Most Used Languages", "  " + "\n  ".join(body))


def tier(value, thresholds):
    # thresholds ascending -> (letter, color)
    grades = [("C", MUTED), ("B", ACCENT), ("A", RING), ("S", "#ffd700")]
    g = grades[0]
    for i, t in enumerate(thresholds):
        if value >= t:
            g = grades[min(i + 1, len(grades) - 1)]
    return g


def svg_trophy(d):
    tiles = [
        ("Stars", d["stars"], [5, 25, 100]),
        ("Commits", d["commits"], [100, 500, 2000]),
        ("Followers", d["followers"], [10, 50, 200]),
        ("Repos", d["repos"], [10, 40, 100]),
        ("PRs", d["prs"], [25, 100, 400]),
        ("Issues", d["issues"], [10, 50, 200]),
    ]
    tw, gap = 70, 7
    n = len(tiles)
    width = 25 * 2 + n * tw + (n - 1) * gap
    body = []
    x = 25
    for label, val, thr in tiles:
        letter, color = tier(val, thr)
        cx = x + tw / 2
        body.append(
            f'<g>'
            f'<rect x="{x}" y="52" width="{tw}" height="86" rx="8" fill="#0b0e14" stroke="{BORDER}"/>'
            f'<circle cx="{cx}" cy="78" r="16" fill="none" stroke="{color}" stroke-width="2.5"/>'
            f'<text x="{cx}" y="84" font-family="{FONT}" font-size="16" font-weight="700" fill="{color}" text-anchor="middle">{letter}</text>'
            f'<text x="{cx}" y="113" font-family="{FONT}" font-size="11" fill="{MUTED}" text-anchor="middle">{escape(label)}</text>'
            f'<text x="{cx}" y="130" font-family="{FONT}" font-size="13" font-weight="700" fill="{TEXT}" text-anchor="middle">{val:,}</text>'
            f'</g>')
        x += tw + gap
    return card(width, 158, "Achievements", "  " + "\n  ".join(body))


def main():
    if not TOKEN:
        raise SystemExit("Missing GH_TOKEN / GITHUB_TOKEN")
    d = fetch()
    os.makedirs("assets", exist_ok=True)
    open("assets/stats.svg", "w").write(svg_stats(d))
    open("assets/top-langs.svg", "w").write(svg_langs(d))
    open("assets/trophy.svg", "w").write(svg_trophy(d))
    print("generated assets/stats.svg, assets/top-langs.svg, assets/trophy.svg")
    print(json.dumps({k: v for k, v in d.items() if k != "top"}, indent=2))


if __name__ == "__main__":
    main()
