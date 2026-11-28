#!/usr/bin/env python3
"""Render the profile SVGs (dark + light) from one source.

    python3 .github/scripts/render.py               # use stats.json
    GH_STATS_TOKEN=... python3 .github/scripts/render.py --github-stats

Outputs (images/):
    header-{dark,light}.svg   whoami: name, role, school
    tree-{dark,light}.svg     ~/after-hours project tree
    wave-{dark,light}.svg     footer divider

Everything is CSS-animated with the final frame as the *base* style, so
`prefers-reduced-motion` (and any renderer without animation support)
shows the finished terminal instead of a blank box. Text lines carry
`textLength`, so column alignment and the typing cursor stay exact no
matter which monospace font the viewer's system picks.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "images"
STATS_FILE = Path(__file__).with_name("stats.json")

W = 822  # GitHub README content width
CW = 8.4  # advance of one monospace glyph at 14px (0.6em)
FONT = ('ui-monospace, SFMono-Regular, "SF Mono", Menlo, "JetBrains Mono", '
        '"DejaVu Sans Mono", Consolas, "Liberation Mono", monospace')

# Six-colour rainbow: window dots and the wave footer (decoration only).
RAINBOW = ["#61BB46", "#FDB827", "#F5821F", "#E03A3E", "#963D97", "#009DDC"]

THEMES = {
    "dark": dict(
        body="#010409", bar="#161B22", border="#30363D", text="#E6EDF3",
        muted="#8B949E", dim="#7D8590", green="#3FB950", blue="#58A6FF",
        amber="#D29922", red="#F85149", purple="#BC8CFF", orange="#F0883E",
        scan="#FFFFFF", scan_op=0.022, glow=0.55,
        rainbow=RAINBOW,
    ),
    "light": dict(
        body="#FFFFFF", bar="#F6F8FA", border="#D0D7DE", text="#1F2328",
        muted="#59636E", dim="#6E7781", green="#1A7F37", blue="#0969DA",
        amber="#9A6700", red="#CF222E", purple="#8250DF", orange="#BC4C00",
        scan="#000000", scan_op=0.016, glow=0.0,
        rainbow=["#4FA83A", "#E8A317", "#E5731A", "#D63236", "#8A3A8B", "#0090C9"],
    ),
}

DEFAULT_STATS = {"created": 2017, "uptime_years": 9, "repos": 118, "private": 41, "releases": {}}

OWNER = "eRgo35"
RELEASE_REPOS = ["okiro", "lyra", "notae", "comma", "ti", "ltx", "graduale-romanum"]


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------

QUERY = """
{
  viewer {
    createdAt
    total: repositories(ownerAffiliations: OWNER) { totalCount }
    private: repositories(privacy: PRIVATE, ownerAffiliations: OWNER) { totalCount }
  }
%s
}
""" % "\n".join(
    f'  r{i}: repository(owner: "{OWNER}", name: "{n}") {{ latestRelease {{ tagName }} }}'
    for i, n in enumerate(RELEASE_REPOS)
)


def short_tag(tag: str) -> str:
    """comma-v0.5.1 / 0.2.0 / v1.0.0 -> v0.5.1 / v0.2.0 / v1.0.0"""
    m = re.search(r"v?(\d[\w.-]*)$", tag)
    return f"v{m.group(1)}" if m else tag


def fetch_github_stats(token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "eRgo35-profile-render",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    v = body["data"]["viewer"]
    created = datetime.fromisoformat(v["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    years = now.year - created.year - ((now.month, now.day) < (created.month, created.day))
    releases = {}
    for i, n in enumerate(RELEASE_REPOS):
        r = body["data"].get(f"r{i}") or {}
        if r.get("latestRelease"):
            releases[n] = short_tag(r["latestRelease"]["tagName"])
    return {
        "releases": releases,
        "created": created.year,
        "uptime_years": years,
        "repos": v["total"]["totalCount"],
        "private": v["private"]["totalCount"],
    }


def load_stats(from_github: bool) -> dict:
    stats = dict(DEFAULT_STATS)
    if STATS_FILE.exists():
        stats.update(json.loads(STATS_FILE.read_text()))
    if from_github:
        token = os.environ.get("GH_STATS_TOKEN")
        if not token:
            print("warning: GH_STATS_TOKEN not set, keeping stats.json", file=sys.stderr)
        else:
            try:
                stats.update(fetch_github_stats(token))
                STATS_FILE.write_text(json.dumps(stats, indent=2) + "\n")
            except Exception as exc:  # keep the render alive on API hiccups
                print(f"warning: stats fetch failed ({exc}), keeping stats.json", file=sys.stderr)
    return stats


# --------------------------------------------------------------------------
# svg helpers
# --------------------------------------------------------------------------

class Doc:
    """Accumulates elements plus per-file @keyframes."""

    def __init__(self, t: dict):
        self.t = t
        self.parts: list[str] = []
        self.frames: list[str] = []
        self._n = 0

    def add(self, s: str) -> None:
        self.parts.append(s)

    def uid(self, p: str = "k") -> str:
        self._n += 1
        return f"{p}{self._n}"

    def keyframes(self, body: str) -> str:
        name = self.uid("k")
        self.frames.append(f"@keyframes {name}{{{body}}}")
        return name


def anim(name: str, dur: float, delay: float = 0.0, fill: str = "both",
         ease: str = "ease-out", extra: str = "") -> str:
    return f'style="animation:{name} {dur:.2f}s {ease} {delay:.2f}s {fill}{extra}"'


def tlen(s: str, size: float = 14) -> float:
    return len(s) * CW * size / 14


def text(x: float, y: float, parts, size: float = 14, style: str = "",
         anchor: str | None = None, weight: str | None = None, cls: str = "") -> str:
    """parts: str or [(str, colour), ...]. Uses textLength for exact width."""
    if isinstance(parts, str):
        parts = [(parts, None)]
    raw = "".join(p for p, _ in parts)
    spans = "".join(
        f'<tspan fill="{c}">{escape(p)}</tspan>' if c else escape(p) for p, c in parts
    )
    a = f' text-anchor="{anchor}"' if anchor else ""
    w = f' font-weight="{weight}"' if weight else ""
    c = f' class="{cls}"' if cls else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{a}{w}{c} '
            f'textLength="{tlen(raw, size):.1f}" lengthAdjust="spacing" {style}>{spans}</text>')


BASE_CSS = """
text{white-space:pre}
.cv{transform:scaleX(0);transform-box:fill-box;transform-origin:100% 50%}
.cur{opacity:0}
@keyframes in{from{opacity:0}}
@keyframes up{from{opacity:0;transform:translateY(8px)}}
@keyframes slide{from{opacity:0;transform:translateX(-14px)}}
@keyframes cover{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@keyframes blink{0%,49.9%{opacity:1}50%,100%{opacity:0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def cursor(t: dict, x: float, y: float, size: float, style: str, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return (f'<rect{c} x="{x:.1f}" y="{y - size * .86:.1f}" width="{tlen("x", size):.1f}" '
            f'height="{size * 1.07:.1f}" fill="{t["text"]}" {style}/>')


def typed(d: Doc, x: float, y: float, s: str, color: str, start: float,
          cps: float = 16, hold_before: float = 0.0, hold_after: float = 0.25,
          size: float = 14) -> float:
    """Text revealed glyph by glyph with a block cursor riding along.

    Returns the time typing finishes.
    """
    t = d.t
    n = max(len(s), 1)
    dur = n / cps
    d.add(text(x, y, [(s, color)], size=size))
    # cover hides the text and shrinks rightwards in n steps
    d.add(f'<rect class="cv" x="{x:.1f}" y="{y - size * .93:.1f}" width="{tlen(s, size)+1:.1f}" height="{size * 1.3:.1f}" '
          f'fill="{t["body"]}" style="animation:cover {dur:.2f}s steps({n},end) {start:.2f}s both"/>')
    # cursor: idle at start, step across, idle at end, then vanish
    total = hold_before + dur + hold_after
    a = hold_before / total * 100
    b = (hold_before + dur) / total * 100
    W_ = tlen(s, size)
    k = d.keyframes(
        f"0%{{opacity:1;transform:translateX(0)}}"
        f"{a:.2f}%{{opacity:1;transform:translateX(0);animation-timing-function:steps({n},end)}}"
        f"{b:.2f}%,100%{{opacity:1;transform:translateX({W_:.1f}px)}}"
    )
    d.add(cursor(t, x, y, size, f'style="animation:{k} {total:.2f}s linear {start-hold_before:.2f}s none"', "cur"))
    return start + dur


def window(t: dict, h: float, title: str, body: str, frames: list[str], label: str) -> str:
    wid = "w"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-label="{escape(label, {'"': '&quot;'})}" font-family='{FONT}'>
<style>{BASE_CSS}{"".join(frames)}</style>
<defs>
<clipPath id="{wid}"><rect x="1" y="1" width="{W-2}" height="{h-2}" rx="11"/></clipPath>
<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="{t["scan"]}" opacity="{t["scan_op"]}"/></pattern>
</defs>
<g clip-path="url(#{wid})">
<rect width="{W}" height="{h}" fill="{t["body"]}"/>
<rect width="{W}" height="36" fill="{t["bar"]}"/>
<rect y="36" width="{W}" height="1" fill="{t["border"]}"/>
<circle cx="22" cy="18" r="6" fill="{t["rainbow"][3]}"/>
<circle cx="42" cy="18" r="6" fill="{t["rainbow"][1]}"/>
<circle cx="62" cy="18" r="6" fill="{t["rainbow"][0]}"/>
{text(W/2, 22.5, [(title, t["muted"])], size=12, anchor="middle")}
{body}
<rect y="37" width="{W}" height="{h-37}" fill="url(#scan)" pointer-events="none"/>
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{h-1}" rx="11.5" fill="none" stroke="{t["border"]}"/>
</svg>
'''


# --------------------------------------------------------------------------
# header: whoami
# --------------------------------------------------------------------------

def header(theme: str, st: dict) -> str:
    t = THEMES[theme]
    d = Doc(t)
    created = st["created"]
    public = st["repos"] - st["private"]
    S = 18  # small line size; README is scaled ~0.44x on phones

    d.add(text(40, 80, [("$ ", t["green"])], size=S))
    t1 = typed(d, 40 + tlen("$ ", S), 80, "whoami", t["text"], .3, cps=18, hold_before=.2, size=S)
    t0 = t1 + .15
    d.add(text(40, 140, [("Michał Czyż", t["text"])], size=46, weight="700", style=anim("up", .45, t0)))
    d.add(text(40, 184, [("JavaScript @ QNT", t["text"]), (" by day · ", t["muted"]),
                         ("Rust", t["orange"]), (" after hours", t["muted"])],
               size=24, style=anim("up", .45, t0 + .12)))
    d.add(text(40, 222, [("MEng · Silesian University of Technology", t["muted"])],
               size=S, style=anim("in", .4, t0 + .3)))
    d.add(text(40, 250, [(f"on GitHub since {created} · {public} public repos", t["muted"])],
               size=S, style=anim("in", .4, t0 + .38)))
    py = 296
    d.add(f'<g style="animation:in .05s linear {t0 + .8:.2f}s both">')
    d.add(text(40, py, [("$ ", t["green"])], size=S))
    d.add(cursor(t, 40 + tlen("$ ", S), py, S, 'style="animation:blink 1.1s steps(1) 0s infinite"'))
    d.add("</g>")
    H = py + 30

    label = (f"Michał Czyż. JavaScript at QNT by day, Rust after hours. "
             f"MEng, Silesian University of Technology. On GitHub since {created}, {public} public repos.")
    return window(t, H, "~ — zsh", "\n".join(d.parts), d.frames, label)


# --------------------------------------------------------------------------
# tree: ~/after-hours
# --------------------------------------------------------------------------

# (repo, description); the version comes from st["releases"]
RUST = [
    ("okiro", "remote wake, manage, shut down"),
    ("lyra", "discord music bot"),
    ("notae", "sheet-music library, android"),
    ("comma", "shell commands from claude"),
    ("ti", "terminal timer"),
    ("ltx", "latex project cli"),
]
MUSIC = [("graduale-romanum", "gregorian chant in lilypond")]


def tree_rows(t: dict, st: dict) -> list[tuple]:
    """(kind, name, colour, version, text) rows in display order."""
    rel = st.get("releases", {})
    rows = [("dir", "rust/", t["orange"], "", "")]
    rows += [("leaf", n, t["text"], rel.get(n, ""), desc) for n, desc in RUST]
    rows += [("dir", "music/", t["purple"], "", "")]
    rows += [("leaf", n, t["text"], rel.get(n, ""), desc) for n, desc in MUSIC]
    rows += [
        ("dir", "kernels/", t["red"], "", "encore · LeafOS · TriOS"),
        ("dir", "ai/", t["blue"], "", "granula · nlp-platform"),
        ("dir", "univ/", t["green"], "", "5 publications 2024–25"),
        ("dir", "also/", t["muted"], "", "zed-dotnet · ah · NoMoreShorts"),
    ]
    return rows


def tree(theme: str, st: dict) -> str:
    t = THEMES[theme]
    d = Doc(t)
    S = 18
    cw = tlen("x", S)
    rows = tree_rows(t, st)
    dirs = [i for i, r in enumerate(rows) if r[0] == "dir"]

    d.add(text(40, 80, [("$ ", t["green"])], size=S, style=anim("in", .05, .2)))
    t1 = typed(d, 40 + 2 * cw, 80, "tree ~/after-hours", t["text"], .5, cps=24, hold_before=.3, size=S)
    y = 122
    d.add(text(40, y, [("~/after-hours", t["amber"])], size=S, weight="700", style=anim("in", .1, t1 + .15)))
    NAME, VER, DESC = 40 + 8 * cw, 40 + 26 * cw, 40 + 35 * cw
    for i, (kind, name, col, ver, desc) in enumerate(rows):
        y += 30
        t0 = t1 + .25 + i * .05
        last_dir = i == dirs[-1]
        if kind == "dir":
            branch = "└── " if last_dir else "├── "
            nx = 40 + 4 * cw
        else:
            last_leaf = i + 1 == len(rows) or rows[i + 1][0] == "dir"
            branch = "│   " + ("└── " if last_leaf else "├── ")
            nx = NAME
        d.add(f'<g style="animation:slide .3s cubic-bezier(.2,.8,.3,1) {t0:.2f}s both">')
        d.add(text(40, y, [(branch, t["dim"])], size=S))
        d.add(text(nx, y, [(name, col)], size=S, weight="700" if kind == "dir" else None))
        if ver:
            d.add(text(VER, y, [(ver, t["green"])], size=S))
        if desc:
            d.add(text(DESC if kind == "leaf" else VER, y, [(desc, t["muted"] if kind == "leaf" else t["text"])], size=S))
        d.add("</g>")
    py = y + 46
    d.add(f'<g style="animation:in .05s linear {t1 + .25 + len(rows) * .05 + .3:.2f}s both">')
    d.add(text(40, py, [("$ ", t["green"])], size=S))
    d.add(cursor(t, 40 + 2 * cw, py, S, 'style="animation:blink 1.1s steps(1) 0s infinite"'))
    d.add("</g>")
    H = py + 30

    parts = []
    for kind, name, _, ver, desc in rows:
        if kind == "dir":
            parts.append(f"{name}{' ' + desc if desc else ''}")
        else:
            parts.append(f"{name} {ver}: {desc}".replace("  ", " "))
    label = "tree ~/after-hours: " + "; ".join(parts) + "."
    return window(t, H, "~/after-hours — zsh", "\n".join(d.parts), d.frames, label)

# --------------------------------------------------------------------------
# wave footer
# --------------------------------------------------------------------------

def sine_path(lam: float, amp: float, mid: float, phase: float = 0.0, step: float = 3.0) -> str:
    pts = []
    x = -lam
    while x <= W + lam + step:
        y = mid + amp * math.sin(2 * math.pi * x / lam + phase)
        pts.append(f"{x:.1f},{y:.1f}")
        x += step
    return "M" + " L".join(pts)


def wave(theme: str) -> str:
    t = THEMES[theme]
    H = 90
    mid = H / 2
    layers = [  # wavelength, amplitude, width, opacity, seconds, direction
        (W / 3, 16, 2.2, 1.0, 5.0, -1),
        (W / 2, 10, 1.4, .55, 9.0, 1),
        (W / 5, 6, 1.0, .35, 4.0, -1),
    ]
    frames = []
    paths = []
    for i, (lam, amp, sw, op, sec, dirn) in enumerate(layers):
        frames.append(f"@keyframes f{i}{{to{{transform:translateX({dirn*lam:.2f}px)}}}}")
        paths.append(f'<path d="{sine_path(lam, amp, mid, i)}" fill="none" stroke="#fff" stroke-width="{sw}" '
                     f'stroke-linecap="round" opacity="{op}" style="animation:f{i} {sec}s linear infinite"/>')
    stops = "".join(f'<stop offset="{i/5:.2f}" stop-color="{c}"/>' for i, c in enumerate(t["rainbow"]))
    glow = ""
    if t["glow"]:
        glow = (f'<g mask="url(#fade)" filter="url(#wglow)" opacity=".5"><rect width="{W}" height="{H}" '
                f'fill="url(#rb)" mask="url(#waves)"/></g>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Rainbow sine waves drifting across, end of profile">
<style>{"".join(frames)}@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style>
<defs>
<linearGradient id="rb" x1="0" x2="1">{stops}</linearGradient>
<linearGradient id="edge" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".18" stop-color="#fff"/><stop offset=".82" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#edge)"/></mask>
<mask id="waves" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">{"".join(paths)}</mask>
<filter id="wglow" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
</defs>
{glow}
<g mask="url(#fade)"><rect width="{W}" height="{H}" fill="url(#rb)" mask="url(#waves)"/></g>
</svg>
'''


# --------------------------------------------------------------------------

def main() -> None:
    st = load_stats("--github-stats" in sys.argv)
    print(f"stats: {st}")
    IMAGES.mkdir(exist_ok=True)
    for theme in THEMES:
        for name, svg in (
            ("header", header(theme, st)),
            ("tree", tree(theme, st)),
            ("wave", wave(theme)),
        ):
            p = IMAGES / f"{name}-{theme}.svg"
            p.write_text(svg, encoding="utf-8")
            print(f"{p.relative_to(ROOT)}  {len(svg)/1024:.1f} KiB")


if __name__ == "__main__":
    main()
