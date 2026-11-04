#!/usr/bin/env python3
"""Wrap cyprieng/github-breakout output in the Encore terminal chrome.

    python3 .github/scripts/skin_breakout.py output/dark.svg  images/breakout-dark.svg  dark
    python3 .github/scripts/skin_breakout.py output/light.svg images/breakout-light.svg light

The generated game is nested untouched inside an <svg> at y=37, so its own
SMIL timeline keeps working; only the paddle/ball blue is swapped for the
Encore amber. Running it on an already-skinned file is refused.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render import FONT, THEMES, W, text  # noqa: E402

BALL = {"dark": "#FDB827", "light": "#BF8700"}


def skin(src: str, theme: str) -> str:
    if 'data-skin="encore"' in src:
        raise SystemExit("input is already skinned; pass the raw action output")
    t = THEMES[theme]
    m = re.match(r"\s*<svg\b([^>]*)>(.*)</svg>\s*$", src, re.S)
    if not m:
        raise SystemExit("unexpected breakout SVG shape")
    attrs, inner = m.groups()
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', attrs)
    gw, gh = (float(vb.group(1)), float(vb.group(2))) if vb else (W, 242.0)
    inner = inner.replace("#1F6FEB", BALL[theme])
    # brick ids are global inside one document: namespace them
    inner = inner.replace('id="brick"', 'id="bk"').replace('href="#brick"', 'href="#bk"')

    h = 37 + gh + 6
    dots = "".join(
        f'<circle cx="{22+i*20}" cy="18" r="6" fill="{t["rainbow"][c]}"/>' for i, c in enumerate((3, 1, 0))
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" data-skin="encore" viewBox="0 0 {W} {h:.0f}" width="{W}" height="{h:.0f}" role="img" aria-label="Breakout game played on the last year of GitHub contributions: an amber ball bounces off the paddle and clears contribution-day bricks." font-family='{FONT}'>
<style>text{{white-space:pre}}</style>
<defs><clipPath id="w"><rect x="1" y="1" width="{W-2}" height="{h-2:.0f}" rx="11"/></clipPath></defs>
<g clip-path="url(#w)">
<rect width="{W}" height="{h:.0f}" fill="{t["body"]}"/>
<rect width="{W}" height="36" fill="{t["bar"]}"/>
<rect y="36" width="{W}" height="1" fill="{t["border"]}"/>
{dots}
{text(W/2, 22.5, [("breakout --input ~/.contributions", t["muted"])], size=12, anchor="middle")}
{text(W-18, 22.5, [("365d", t["dim"])], size=11, anchor="end")}
<svg x="{(W-gw)/2:.1f}" y="37" width="{gw:.0f}" height="{gh:.0f}" viewBox="0 0 {gw:.0f} {gh:.0f}" overflow="hidden">{inner}</svg>
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{h-1:.0f}" rx="11.5" fill="none" stroke="{t["border"]}"/>
</svg>
'''


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[3] not in THEMES:
        raise SystemExit(__doc__)
    src, dst, theme = sys.argv[1:]
    out = skin(Path(src).read_text(encoding="utf-8"), theme)
    Path(dst).write_text(out, encoding="utf-8")
    print(f"{dst}  {len(out)/1024:.1f} KiB")


if __name__ == "__main__":
    main()
