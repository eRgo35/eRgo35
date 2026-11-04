#!/usr/bin/env python3
"""Render the profile SVGs (dark + light) from one source.

    python3 .github/scripts/render.py               # use stats.json
    GH_STATS_TOKEN=... python3 .github/scripts/render.py --github-stats

Outputs (images/):
    header-{dark,light}.svg   boot -> splash -> login -> neofetch
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

# Classic six-colour rainbow: the Encore accent palette.
RAINBOW = ["#61BB46", "#FDB827", "#F5821F", "#E03A3E", "#963D97", "#009DDC"]

THEMES = {
    "dark": dict(
        body="#010409", bar="#161B22", border="#30363D", text="#E6EDF3",
        muted="#8B949E", dim="#484F58", green="#3FB950", blue="#58A6FF",
        amber="#D29922", red="#F85149", purple="#BC8CFF", orange="#F0883E",
        scan="#FFFFFF", scan_op=0.022, shine=0.30, glow=0.55,
        rainbow=RAINBOW, status_fg="#010409",
    ),
    "light": dict(
        body="#FFFFFF", bar="#F6F8FA", border="#D0D7DE", text="#1F2328",
        muted="#59636E", dim="#AFB8C1", green="#1A7F37", blue="#0969DA",
        amber="#9A6700", red="#CF222E", purple="#8250DF", orange="#BC4C00",
        scan="#000000", scan_op=0.016, shine=0.55, glow=0.0,
        rainbow=["#4FA83A", "#E8A317", "#E5731A", "#D63236", "#8A3A8B", "#0090C9"],
        status_fg="#FFFFFF",
    ),
}

DEFAULT_STATS = {"created": 2017, "uptime_years": 9, "repos": 118, "private": 41}


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
}
"""


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
    return {
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
.gx{transform-box:fill-box;transform-origin:0 50%}
.fb{transform-box:fill-box;transform-origin:50% 50%}
.cur{opacity:0}
.scene{opacity:0}
@keyframes in{from{opacity:0}}
@keyframes up{from{opacity:0;transform:translateY(6px)}}
@keyframes slide{from{opacity:0;transform:translateX(-14px)}}
@keyframes cover{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@keyframes grow{from{transform:scaleX(0)}}
@keyframes win{0%,100%{opacity:1}}
@keyframes blink{0%,49.9%{opacity:1}50%,100%{opacity:0}}
@keyframes pop{0%{opacity:0;transform:translateY(-22px) scale(.85)}65%{opacity:1;transform:translateY(3px) scale(1.02)}100%{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def typed(d: Doc, x: float, y: float, s: str, color: str, start: float,
          cps: float = 16, hold_before: float = 0.0, hold_after: float = 0.25) -> float:
    """Text revealed glyph by glyph with a block cursor riding along.

    Returns the time typing finishes.
    """
    t = d.t
    n = max(len(s), 1)
    dur = n / cps
    d.add(text(x, y, [(s, color)]))
    # cover hides the text and shrinks rightwards in n steps
    d.add(f'<rect class="cv" x="{x:.1f}" y="{y-13:.1f}" width="{tlen(s)+1:.1f}" height="18" '
          f'fill="{t["body"]}" style="animation:cover {dur:.2f}s steps({n},end) {start:.2f}s both"/>')
    # cursor: idle at start, step across, idle at end, then vanish
    total = hold_before + dur + hold_after
    a = hold_before / total * 100
    b = (hold_before + dur) / total * 100
    W_ = n * CW
    k = d.keyframes(
        f"0%{{opacity:1;transform:translateX(0)}}"
        f"{a:.2f}%{{opacity:1;transform:translateX(0);animation-timing-function:steps({n},end)}}"
        f"{b:.2f}%,100%{{opacity:1;transform:translateX({W_:.1f}px)}}"
    )
    d.add(f'<rect class="cur" x="{x:.1f}" y="{y-12:.1f}" width="8.4" height="15" fill="{t["text"]}" '
          f'style="animation:{k} {total:.2f}s linear {start-hold_before:.2f}s none"/>')
    return start + dur


def window(t: dict, h: float, title: str, right: str, body: str, frames: list[str],
           label: str, extra_defs: str = "", status: str = "") -> str:
    wid = "w"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-label="{escape(label, {'"': '&quot;'})}" font-family='{FONT}'>
<style>{BASE_CSS}{"".join(frames)}</style>
<defs>
<clipPath id="{wid}"><rect x="1" y="1" width="{W-2}" height="{h-2}" rx="11"/></clipPath>
<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="{t["scan"]}" opacity="{t["scan_op"]}"/></pattern>
{extra_defs}
</defs>
<g clip-path="url(#{wid})">
<rect width="{W}" height="{h}" fill="{t["body"]}"/>
<rect width="{W}" height="36" fill="{t["bar"]}"/>
<rect y="36" width="{W}" height="1" fill="{t["border"]}"/>
<circle cx="22" cy="18" r="6" fill="{t["rainbow"][3]}"/>
<circle cx="42" cy="18" r="6" fill="{t["rainbow"][1]}"/>
<circle cx="62" cy="18" r="6" fill="{t["rainbow"][0]}"/>
{text(W/2, 22.5, [(title, t["muted"])], size=12, anchor="middle")}
{text(W-18, 22.5, [(right, t["dim"])], size=11, anchor="end")}
{body}
{status}
<rect y="37" width="{W}" height="{h-37}" fill="url(#scan)" pointer-events="none"/>
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{h-1}" rx="11.5" fill="none" stroke="{t["border"]}"/>
</svg>
'''


# --------------------------------------------------------------------------
# pixel art
# --------------------------------------------------------------------------

GLYPHS = {
    "e": [".###.", "#...#", "#####", "#....", "#...#", ".###."],
    "n": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#"],
    "c": [".####", "#....", "#....", "#....", "#....", ".####"],
    "o": [".###.", "#...#", "#...#", "#...#", "#...#", ".###."],
    "r": ["#.###", "##...", "#....", "#....", "#....", "#...."],
}

LOGO = [  # 10 x 12, six two-row stripes
    "..######..",
    ".########.",
    "###....###",
    "##......##",
    "##......##",
    "##########",
    "##########",
    "##........",
    "##........",
    "###.....##",
    ".########.",
    "..######..",
]


def pixels(rows, x0, y0, cell, gap=0.0) -> list[tuple[float, float, int]]:
    out = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "#":
                out.append((x0 + c * cell, y0 + r * cell, r))
    return out


def rects(px, cell, fill, inset=0.0) -> str:
    s = cell - inset
    return "".join(
        f'<rect x="{x+inset/2:.1f}" y="{y+inset/2:.1f}" width="{s:.1f}" height="{s:.1f}" fill="{fill}"/>'
        for x, y, _ in px
    )


# --------------------------------------------------------------------------
# header: boot -> splash -> session (neofetch)
# --------------------------------------------------------------------------

def header(theme: str, st: dict) -> str:
    t = THEMES[theme]
    d = Doc(t)
    H = 500
    years, repos, priv, created = st["uptime_years"], st["repos"], st["private"], st["created"]
    yrs = f"{years} year{'' if years == 1 else 's'}"

    # ---- scene 1: POST ---------------------------------------------------
    BOOT_END = 1.95
    d.add(f'<g class="scene" style="animation:{d.keyframes("0%,90%{opacity:1}100%{opacity:0}")} {BOOT_END:.2f}s linear 0s both">')
    d.add(text(40, 70, [("EncoreBIOS v1.04 · (C) 2026 encore-industries", t["muted"])], style=anim("in", .1, .08)))
    rows = [
        (100, "CPU     : Encode E35 “Cerebrum” 8-core @ 3.90GHz", .22, .36),
        (148, "Detect  : hda ENCORE-KERNEL · hdb RUST-TOOLS", 1.0, 1.1),
        (172, "Boot    : encoreldr → /boot/encore.img", 1.16, None),
    ]
    for y, s, t0, ok in rows:
        d.add(text(40, y, [(s, t["text"])], style=anim("in", .08, t0)))
        if ok:
            d.add(text(782, y, [("[  OK  ]", t["green"])], anchor="end", style=anim("in", .08, ok)))
    # memory counter
    counts = ["   640K", "  4096K", "  8192K", " 16384K", " 24576K", " 32768K"]
    for i, c in enumerate(counts):
        t0 = .45 + i * .08
        last = i == len(counts) - 1
        s = f"Memory  : {c}"
        if last:
            d.add(text(40, 124, [(s, t["text"])], style=anim("in", .01, t0)))
        else:
            d.add(text(40, 124, [(s, t["text"])], cls="cur",
                       style=f'style="animation:win .08s linear {t0:.2f}s none"'))
    d.add(text(782, 124, [("[  OK  ]", t["green"])], anchor="end", style=anim("in", .08, .95)))
    # progress bar
    d.add(f'<rect x="40" y="186" width="300" height="8" rx="2" fill="none" stroke="{t["border"]}" {anim("in", .1, 1.16)}/>')
    d.add(f'<rect class="gx" x="40" y="186" width="300" height="8" rx="2" fill="{t["green"]}" '
          f'style="animation:grow .5s cubic-bezier(.5,0,.3,1) 1.22s both"/>')
    d.add(text(40, H - 22, [("Press DEL to enter SETUP · F12 boot menu", t["dim"])], size=11, style=anim("in", .1, .5)))
    d.add("</g>")

    # CRT roll between scenes
    for t0 in (BOOT_END - .1, 3.62):
        k = d.keyframes("0%{opacity:0;transform:translateY(0)}15%{opacity:.5}85%{opacity:.5}100%{opacity:0;transform:translateY(460px)}")
        d.add(f'<rect x="0" y="37" width="{W}" height="3" fill="{t["text"]}" opacity="0" style="animation:{k} .35s linear {t0:.2f}s none"/>')

    # ---- scene 2: splash -------------------------------------------------
    S0, S1 = 2.0, 3.72
    k = d.keyframes("0%{opacity:0}5%,92%{opacity:1}100%{opacity:0}")
    d.add(f'<g class="scene" style="animation:{k} {S1-S0:.2f}s linear {S0:.2f}s both">')
    cell = 12
    word = "encore"
    gw = 5 * cell
    gap = 20
    total_w = len(word) * gw + (len(word) - 1) * gap
    x0 = (W - total_w) / 2
    y0 = 180
    glow = []
    for i, ch in enumerate(word):
        px = pixels(GLYPHS[ch], x0 + i * (gw + gap), y0, cell)
        col = t["rainbow"][i % 6]
        glow.append(rects(px, cell, col))
        d.add(f'<g class="fb" style="animation:pop .5s cubic-bezier(.3,.7,.4,1) {S0+.12+i*.09:.2f}s both">{rects(px, cell, col, inset=1)}</g>')
    if t["glow"]:
        d.add(f'<g filter="url(#glow)" opacity="{t["glow"]}" style="animation:in .6s ease-out {S0+.7:.2f}s both">{"".join(glow)}</g>')
    d.add(text(W / 2, 300, [("encore os", t["text"]), ("  v1.0  ·  encore-industries", t["muted"])],
               size=14, anchor="middle", style=anim("up", .4, S0 + .75)))
    for i in range(3):  # loading pips
        k = d.keyframes("0%,100%{opacity:.25}50%{opacity:1}")
        d.add(f'<rect x="{W/2-26+i*20:.1f}" y="330" width="12" height="12" fill="{t["rainbow"][(i*2+5)%6]}" opacity=".25" '
              f'style="animation:{k} .6s ease-in-out {S0+.9+i*.15:.2f}s 3"/>')
    d.add("</g>")

    # ---- scene 3: session ------------------------------------------------
    T0 = 3.8
    # everything in the session (incl. typing covers) stays hidden until T0
    d.add(f'<g style="animation:in .15s linear {T0:.2f}s both">')
    d.add(text(40, 68, [("encore login: ", t["muted"])]))
    t1 = typed(d, 40 + tlen("encore login: "), 68, "mike", t["green"], T0 + .35, cps=12, hold_before=.3)
    d.add(text(40, 90, [("Password: ", t["muted"])], style=anim("in", .05, t1 + .2)))
    t2 = typed(d, 40 + tlen("Password: "), 90, "••••••••", t["text"], t1 + .35, cps=28, hold_before=.1, hold_after=.15)
    d.add(text(40, 112, [("Welcome to encore os v1.0 (tty1) · account created ", t["dim"]),
                         (str(created), t["muted"]), (" · uptime ", t["dim"]), (yrs, t["muted"])],
               size=12, style=anim("in", .2, t2 + .25)))
    t3s = t2 + .55
    d.add(text(40, 144, [("$ ", t["green"])], style=anim("in", .05, t3s)))
    t3 = typed(d, 40 + 2 * CW, 144, "neofetch", t["text"], t3s + .3, cps=14, hold_before=.25)

    # neofetch block
    N0 = t3 + .3
    LX, LY, LC = 52, 214, 11  # logo x, y, cell (centred on the info block)
    stripes = {}
    for x, y, r in pixels(LOGO, LX, LY, LC):
        stripes.setdefault(r // 2, []).append((x, y, r))
    clip = []
    for s_i in range(6):
        px = stripes[s_i]
        clip.append(rects(px, LC, "#000"))
        d.add(f'<g style="animation:slide .35s cubic-bezier(.2,.8,.3,1) {N0+s_i*.07:.2f}s both">{rects(px, LC, t["rainbow"][s_i], inset=1)}</g>')
    # shimmer, clipped to the logo pixels
    d.frames.append("@keyframes shine{0%{transform:translateX(-90px)}28%,100%{transform:translateX(190px)}}")
    d.add(f'<g clip-path="url(#logoClip)"><polygon points="{LX},{LY-10} {LX+26},{LY-10} {LX-14},{LY+150} {LX-40},{LY+150}" '
          f'fill="#FFFFFF" opacity="{t["shine"]}" style="transform:translateX(-90px);animation:shine 5.5s ease-in-out {N0+1.2:.2f}s infinite"/></g>')
    logo_clip = f'<clipPath id="logoClip">{"".join(clip)}</clipPath>'

    IX, KX = 204, 296  # info column, value column
    info = [
        ("Name", [("Michał Czyż", t["text"])]),
        ("OS", [("encore os v1.0 x86_64", t["text"])]),
        ("Host", [("Silesian University of Technology · MEng", t["text"])]),
        ("Kernel", [("encore · LeafOS · TriOS", t["text"])]),
        ("Uptime", [(yrs, t["text"]), (f" (since {created})", t["muted"])]),
        ("Repos", [(str(repos), t["text"]), (f" · {priv} private, waiting to ship", t["muted"])]),
        ("Packages", [("rust · javascript · docker · rocky · fedora", t["text"])]),
        ("Day job", [("JavaScript @ QNT", t["text"])]),
        ("Now", [("Encore OS, Rust tooling, self-hosted boxes", t["text"])]),
    ]
    y = 172
    d.add(text(IX, y, [("mike", t["green"]), ("@", t["muted"]), ("encore", t["blue"])], weight="600",
               style=anim("in", .15, N0 + .1)))
    y += 21
    d.add(text(IX, y, [("─" * 11, t["dim"])], style=anim("in", .15, N0 + .14)))
    for i, (k_, v) in enumerate(info):
        y += 21
        t0 = N0 + .2 + i * .06
        d.add(f'<g style="animation:up .25s ease-out {t0:.2f}s both">')
        d.add(text(IX, y, [(k_, t["blue"])], weight="600"))
        d.add(text(KX, y, v))
        d.add("</g>")
    y += 24
    for i, col in enumerate(t["rainbow"] + [t["text"], t["dim"]]):
        d.add(f'<rect x="{IX+i*30}" y="{y-6}" width="26" height="14" rx="2" fill="{col}" '
              f'{anim("in", .2, N0 + .8 + i * .05)}/>')

    # final prompt
    P0 = N0 + 1.3
    py = y + 42
    d.add(f'<g style="animation:in .05s linear {P0:.2f}s both">')
    d.add(text(40, py, [("$ ", t["green"])]))
    d.add(f'<rect x="{40+2*CW:.1f}" y="{py-12}" width="8.4" height="15" fill="{t["text"]}" '
          f'style="animation:blink 1.1s steps(1) 0s infinite"/>')
    d.add("</g>")
    d.add("</g>")  # session

    # tmux-ish status line
    sy = H - 26
    status = (
        f'<g style="animation:in .2s linear {T0:.2f}s both">'
        f'<rect y="{sy}" width="{W}" height="26" fill="{t["bar"]}"/>'
        f'<rect y="{sy}" width="{W}" height="1" fill="{t["border"]}"/>'
        f'<rect x="0" y="{sy+1}" width="78" height="25" fill="{t["green"]}"/>'
        + text(14, sy + 17.5, [("encore", t["status_fg"])], size=12, weight="700")
        + text(92, sy + 17.5, [("0:zsh*", t["text"]), ("  1:rust  2:infra  3:ai", t["muted"])], size=12)
        + text(W - 16, sy + 17.5, [(f"{repos} repos", t["muted"]), ("  ·  ", t["dim"]),
                                   (f"up {years}y", t["muted"]), ("  ·  ", t["dim"]), ("tty1", t["muted"])],
               size=12, anchor="end")
        + "</g>"
    )

    defs = logo_clip + ('<filter id="glow" x="-20%" y="-60%" width="140%" height="220%">'
                        '<feGaussianBlur stdDeviation="9"/></filter>')
    label = (f"Animated Encore OS terminal for Michał Czyż (mike). A BIOS posts and boots encore os, "
             f"a rainbow pixel 'encore' splash appears, mike logs in and runs neofetch: OS encore os v1.0; "
             f"host Silesian University of Technology, MEng; kernels encore, LeafOS and TriOS; uptime {yrs} "
             f"since {created}; {repos} repos, {priv} private; rust, javascript, docker, rocky, fedora; "
             f"day job JavaScript at QNT; now working on Encore OS, Rust tooling and self-hosted boxes.")
    return window(t, H, "mike@encore: ~", "tty1", "\n".join(d.parts), d.frames, label, defs, status)


# --------------------------------------------------------------------------
# tree
# --------------------------------------------------------------------------

def tree(theme: str, st: dict) -> str:
    t = THEMES[theme]
    d = Doc(t)
    R = t["rainbow"]
    dirs = [
        ("rust/", R[2], "ah · ltx · okiro · Server-Manager"),
        ("kernels/", R[3], "encore · LeafOS · TriOS"),
        ("infra/", R[5], "self-hosted · rocky · fedora · docker · dots"),
        ("js/", R[1], "loom · james · QNT by day"),
        ("ai/", R[4], "granula · anima · nlp-platform"),
        ("univ/", R[0], "5 publications 2024–25"),
        ("archive/", t["dim"], "lyra · ti · ascii"),
    ]
    d.add(text(40, 68, [("$ ", t["green"])], style=anim("in", .05, .5)))
    t1 = typed(d, 40 + 2 * CW, 68, "tree -L 2 ~/after-hours", t["text"], 1.0, cps=22, hold_before=.5)
    y = 102
    d.add(text(40, y, [("~/after-hours", t["amber"])], weight="600", style=anim("in", .1, t1 + .2)))
    for i, (name, col, items) in enumerate(dirs):
        y += 24
        last = i == len(dirs) - 1
        t0 = t1 + .3 + i * .08
        branch = "└── " if last else "├── "
        dimmed = name == "archive/"
        d.add(f'<g style="animation:slide .3s cubic-bezier(.2,.8,.3,1) {t0:.2f}s both">')
        d.add(text(48, y, [(branch, t["dim"])]))
        d.add(f'<rect x="{48+4*CW:.1f}" y="{y-9}" width="4" height="10" rx="1" fill="{col}"/>')
        d.add(text(48 + 4 * CW + 10, y, [(name, t["muted"] if dimmed else col)], weight="600"))
        d.add(text(196, y, [(items, t["muted"] if dimmed else t["text"])]))
        d.add("</g>")
    y += 34
    d.add(text(48, y, [("7 directories · ", t["muted"]), (str(st["private"]), t["text"]),
                       (" private repos waiting to ship", t["muted"])], size=13,
               style=anim("in", .25, t1 + .3 + len(dirs) * .08 + .2)))
    py = y + 32
    H = py + 26
    P0 = t1 + 1.3
    d.add(f'<g style="animation:in .05s linear {P0:.2f}s both">')
    d.add(text(40, py, [("$ ", t["green"])]))
    d.add(f'<rect x="{40+2*CW:.1f}" y="{py-12}" width="8.4" height="15" fill="{t["text"]}" '
          f'style="animation:blink 1.1s steps(1) 0s infinite"/>')
    d.add("</g>")
    label = ("Terminal running tree on ~/after-hours. rust: ah, ltx, okiro, Server-Manager. "
             "kernels: encore, LeafOS, TriOS. infra: self-hosted, rocky, fedora, docker, dots. "
             "js: loom, james, QNT by day. ai: granula, anima, nlp-platform. "
             "univ: 5 publications 2024–25. archive: lyra, ti, ascii. "
             f"7 directories, {st['private']} private repos waiting to ship.")
    return window(t, H, "mike@encore: ~/after-hours", "zsh", "\n".join(d.parts), d.frames, label)


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
