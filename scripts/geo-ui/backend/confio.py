from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SETS = ("blocked-sites", "only-ru")
SET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
DOMAIN_RE = re.compile(
    r"^([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
TLD_RE = re.compile(r"^[A-Za-z]{2,}$")
CIDR_RE = re.compile(
    r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    r"(/(3[0-2]|[12]?[0-9]))?$"
)
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class Entry:
    set_name: str
    value: str
    kind: str


@dataclass
class Group:
    slug: str
    path: Path
    title: str
    description: str
    title_from_file: bool
    entries: list[Entry] = field(default_factory=list)


def classify_line(line: str) -> str | None:
    s = line.strip()
    low = s.lower()
    if low.startswith("geosite:") and low[8:].strip():
        return "geosite"
    if low.startswith("geoip:") and low[6:].strip():
        return "geoip"
    if CIDR_RE.match(s):
        return "cidr"
    if DOMAIN_RE.match(s) or TLD_RE.match(s):
        return "domain"
    return None


def canonicalize_value(line: str, kind: str | None = None) -> str:
    s = line.strip()
    k = kind or classify_line(s)
    if k in ("geosite", "geoip"):
        return s.lower()
    return s


def parse_file(path: Path) -> Group:
    slug = path.stem
    title = slug
    title_from_file = False
    desc_parts: list[str] = []
    entries: list[Entry] = []
    cur_set = ""
    in_header = True
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip().replace("\r", "")
        if in_header:
            if not stripped:
                continue
            if stripped.startswith("#"):
                c = stripped[1:].strip()
                if not title_from_file:
                    title = c or slug
                    title_from_file = True
                elif c:
                    desc_parts.append(c)
                continue
            in_header = False
        if not stripped or stripped.startswith("#"):
            continue
        line = stripped.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            s = line[1:-1].replace(" ", "")
            cur_set = s if SET_RE.match(s) else ""
            continue
        if line.startswith("include"):
            continue
        kind = classify_line(line)
        if not kind or not cur_set:
            continue
        entries.append(Entry(cur_set, canonicalize_value(line, kind), kind))
    return Group(slug, path, title, "\n".join(desc_parts), title_from_file, entries)


def write_file(group: Group) -> None:
    lines: list[str] = []
    if group.title_from_file:
        lines.append("# " + group.title)
        if group.description:
            for d in group.description.split("\n"):
                lines.append("# " + d)
        lines.append("")
    by_set: dict[str, list[str]] = {s: [] for s in SETS}
    extra: dict[str, list[str]] = {}
    for e in group.entries:
        val = e.value
        (by_set[e.set_name] if e.set_name in by_set else extra.setdefault(e.set_name, [])).append(val)
    for s in SETS:
        if not by_set[s]:
            continue
        lines.append("[" + s + "]")
        lines.extend(by_set[s])
        lines.append("")
    for s, vals in extra.items():
        lines.append("[" + s + "]")
        lines.extend(vals)
        lines.append("")
    group.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def list_groups(dir_path: Path) -> list[Group]:
    return [parse_file(p) for p in sorted(dir_path.glob("*.conf"))]


def slugify(title: str) -> str:
    s = SLUG_RE.sub("-", title.lower()).strip("-")
    return s or "group"


def unique_slug(dir_path: Path, title: str) -> str:
    base = slugify(title)
    slug = base
    n = 2
    while (dir_path / (slug + ".conf")).exists():
        slug = "%s-%d" % (base, n)
        n += 1
    return slug
