#!/usr/bin/env python3
"""Rewrite the account stats baked into the boot-header SVGs.

    GH_STATS_TOKEN=... python3 .github/scripts/update_header_counts.py [SVG ...]

Updates three values from the token's user:
  * total repos    -- repositories owned by the user (public + private)
  * private repos  -- the private subset of those
  * uptime         -- whole years since the account was created

Private repos are only visible to a token that has access to them; the
default Actions GITHUB_TOKEN does not, so a PAT is required and the script
refuses to run without one.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

DEFAULT_SVGS = [
    "images/header-boot-dark.svg",
    "images/header-boot-light.svg",
]

QUERY = """
{
  viewer {
    createdAt
    total: repositories(ownerAffiliations: OWNER) { totalCount }
    private: repositories(privacy: PRIVATE, ownerAffiliations: OWNER) { totalCount }
  }
}
"""

# "uptime 9 years · 176 repos</text>"  and  "89 private repos waiting to ship"
UPTIME_RE = re.compile(r"(?<=uptime )\d+ years?")
TOTAL_RE = re.compile(r"\d+(?= repos<)")
PRIVATE_RE = re.compile(r"\d+(?= private repos waiting to ship)")


def fetch_stats(token: str) -> tuple[int, int, int]:
    """Return (total repos, private repos, whole years since account creation)."""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "update-header-counts",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    viewer = body["data"]["viewer"]

    created = datetime.fromisoformat(viewer["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    years = now.year - created.year - ((now.month, now.day) < (created.month, created.day))
    return viewer["total"]["totalCount"], viewer["private"]["totalCount"], years


def patch(path: str, total: int, private: int, years: int) -> bool:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    out, n_up = UPTIME_RE.subn(f"{years} year{'' if years == 1 else 's'}", src)
    out, n_total = TOTAL_RE.subn(str(total), out)
    out, n_private = PRIVATE_RE.subn(str(private), out)
    if (n_up, n_total, n_private) != (1, 1, 1):
        sys.exit(f"{path}: expected 1 uptime + 1 total + 1 private match, "
                 f"found {n_up} + {n_total} + {n_private}")
    if out == src:
        return False
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    return True


def main() -> None:
    token = os.environ.get("GH_STATS_TOKEN")
    if not token:
        sys.exit("GH_STATS_TOKEN is not set (PAT needed to see private repos)")
    total, private, years = fetch_stats(token)
    print(f"total={total} private={private} uptime={years}y")
    for path in sys.argv[1:] or DEFAULT_SVGS:
        print(f"{path}: {'updated' if patch(path, total, private, years) else 'unchanged'}")


if __name__ == "__main__":
    main()
