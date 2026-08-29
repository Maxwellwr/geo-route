from __future__ import annotations

import re
import subprocess

LINE_RE = re.compile(
    r"^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/\d+"
)


def _is_private(ip: str) -> bool:
    a, b = (int(x) for x in ip.split(".")[:2])
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


def lan_ipv4(addr_text: str, route_text: str = "") -> str:
    wan = set()
    for m in re.finditer(r"\bdev\s+(\S+)", route_text):
        wan.add(m.group(1))

    parsed = []
    for line in addr_text.splitlines():
        m = LINE_RE.search(line)
        if not m:
            continue
        iface, ip = m.group(1), m.group(2)
        iface_base = iface.split("@")[0]
        parsed.append((iface_base, ip))
        if iface_base == "br0":
            return ip

    for iface, ip in parsed:
        if iface in ("lo", "nwg0") or iface in wan:
            continue
        if _is_private(ip):
            return ip

    raise RuntimeError("no LAN IPv4 (br0 / private) found")


def detect_lan_ipv4() -> str:
    addr = subprocess.check_output(["ip", "-4", "-o", "addr", "show"], text=True)
    try:
        route = subprocess.check_output(["ip", "route", "show", "default"], text=True)
    except subprocess.CalledProcessError:
        route = ""
    return lan_ipv4(addr, route)
