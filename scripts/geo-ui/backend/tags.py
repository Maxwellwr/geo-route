from __future__ import annotations

import subprocess
from pathlib import Path

# geoview has no -action list; extract without -list dumps all codes.
LIST_ARGS = ["-action", "extract"]
GEOVIEW = "geoview"


def parse_tag_list(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" in s:
            continue
        out.append(s.split()[0].lower())
    return out


def list_tags(
    kind: str,
    dat: Path,
    geoview_output: str | None = None,
) -> list[str]:
    if geoview_output is not None:
        return parse_tag_list(geoview_output)

    cmd = [GEOVIEW, "-type", kind, *LIST_ARGS, "-input", str(dat)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return parse_tag_list(proc.stdout)


def search_tags(items: list[str], query: str, limit: int = 30) -> list[str]:
    q = (query or "").strip().lower()
    if len(q) < 2 or limit <= 0:
        return []

    prefix = []
    contains = []
    for tag in items:
        value = tag.lower()
        if value.startswith(q):
            prefix.append(tag)
        elif q in value:
            contains.append(tag)

    return (prefix + contains)[:limit]
