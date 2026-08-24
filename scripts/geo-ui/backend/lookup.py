from __future__ import annotations

import re
import subprocess

IPV4_RE = re.compile(
    r"\b((?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)


def parse_a_records(text: str) -> list[str]:
    seen: list[str] = []
    for m in IPV4_RE.finditer(text or ""):
        ip = m.group(0)
        if ip.startswith("127."):
            continue
        if ip not in seen:
            seen.append(ip)
    return seen


def run_query(domain: str) -> str:
    commands = (
        ["dig", "+time=2", "+tries=1", "+short", "A", domain, "@127.0.0.1"],
        ["nslookup", domain, "127.0.0.1"],
    )
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            return out
    return ""


def iter_lookup(domains: list[str]) -> list[str]:
    lines: list[str] = []
    for raw in domains:
        domain = (raw or "").strip().lower()
        if not domain:
            continue
        ips = parse_a_records(run_query(domain))
        if ips:
            lines.append("lookup %s → %s" % (domain, " ".join(ips)))
        else:
            lines.append("lookup %s → (нет A)" % domain)
    return lines
