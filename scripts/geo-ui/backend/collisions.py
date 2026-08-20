from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from confio import Entry, Group


@dataclass
class Collision:
    value: str
    hits: list[tuple[str, str]]


def norm_value(entry: Entry) -> str:
    v = entry.value.strip()
    if entry.kind in ("domain", "geosite", "geoip"):
        return v.lower()
    return v


def find_collisions(groups: list[Group]) -> list[Collision]:
    idx: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for g in groups:
        for e in g.entries:
            idx[norm_value(e)].append((g.slug, e.set_name))
    out = []
    for value, hits in sorted(idx.items()):
        if len(hits) > 1:
            out.append(Collision(value, hits))
    return out
