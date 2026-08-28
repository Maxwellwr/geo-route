#!/opt/bin/python3
from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections import defaultdict

DNSMASQ_DIR = pathlib.Path("/opt/etc/dnsmasq.d")
GEO_IMPORT = pathlib.Path("/opt/etc/geo/geo.d/imported-dnsmasq.conf")
RESERVED_TARGETS = ("blocked-sites", "only-ru")
DOMAIN_RE = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")
TLD_RE = re.compile(r"^[A-Za-z]{2,}$")
SET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
LINE_RE = re.compile(r"^(?P<indent>\s*)ipset=(?P<body>\S+)(?P<suffix>.*?)(?P<nl>\r?\n)?$")


@dataclasses.dataclass
class Directive:
    raw: str
    indent: str
    domains: list[str]
    sets: list[str]
    suffix: str
    newline: str
    supported: bool
    unsupported_domains: list[str]


@dataclasses.dataclass
class FoundDirective:
    path: pathlib.Path
    line_no: int
    directive: Directive


@dataclasses.dataclass
class IpsetState:
    set_type: str
    references: int
    members: list[str]


def parse_ipset_line(line: str) -> Directive | None:
    m = LINE_RE.match(line)
    if not m:
        return None
    body = m.group("body")
    if not body.startswith("/"):
        return None
    parts = body.split("/")
    if len(parts) < 3 or parts[0] != "":
        return None
    domains = [p for p in parts[1:-1] if p]
    sets = [s for s in parts[-1].split(",") if s]
    if not domains or not sets:
        return None
    bad_domains = [d for d in domains if not (DOMAIN_RE.match(d) or TLD_RE.match(d))]
    supported = not bad_domains and all(SET_RE.match(s) for s in sets)
    return Directive(
        raw=line,
        indent=m.group("indent"),
        domains=domains,
        sets=sets,
        suffix=m.group("suffix") or "",
        newline=m.group("nl") or "",
        supported=supported,
        unsupported_domains=bad_domains,
    )


def rewrite_directive(d: Directive, replacements: dict[str, str | None]) -> str:
    new_sets: list[str] = []
    for s in d.sets:
        if s not in replacements:
            new_sets.append(s)
            continue
        repl = replacements[s]
        if repl is not None and repl not in new_sets:
            new_sets.append(repl)
    if not new_sets:
        return ""
    body = "/" + "/".join(d.domains) + "/" + ",".join(new_sets)
    return f"{d.indent}ipset={body}{d.suffix}{d.newline}"


def scan_dnsmasq_dir(root: pathlib.Path = DNSMASQ_DIR) -> list[FoundDirective]:
    out: list[FoundDirective] = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.conf")):
        if path.name == "geo-generated.conf" or path.name.endswith(".geo-route.bak"):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeError):
            continue
        for i, line in enumerate(lines, 1):
            d = parse_ipset_line(line)
            if d is not None:
                out.append(FoundDirective(path, i, d))
    return out


def _read_import_config(path: pathlib.Path) -> dict[str, set[str]]:
    data: dict[str, set[str]] = {s: set() for s in RESERVED_TARGETS}
    if not path.is_file():
        return data
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            current = name if name in data else None
            continue
        if current and (DOMAIN_RE.match(line) or TLD_RE.match(line)):
            data[current].add(line)
    return data


def merge_import_config(path: pathlib.Path, additions: dict[str, set[str]]) -> None:
    data = _read_import_config(path)
    for target, domains in additions.items():
        if target in data:
            data[target].update(domains)
    lines = ["# Imported from existing dnsmasq ipset directives", ""]
    for target in RESERVED_TARGETS:
        if not data[target]:
            continue
        lines.append(f"[{target}]")
        lines.extend(sorted(data[target]))
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_ipset_list(text: str) -> IpsetState:
    set_type = ""
    references = 0
    members: list[str] = []
    in_members = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Type:"):
            set_type = line.split(":", 1)[1].strip()
        elif line.startswith("References:"):
            try:
                references = int(line.split(":", 1)[1].strip())
            except ValueError:
                references = 0
        elif line == "Members:":
            in_members = True
        elif in_members and line:
            members.append(line.split()[0])
    return IpsetState(set_type=set_type, references=references, members=members)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def get_ipset_state(name: str) -> IpsetState | None:
    p = _run("ipset", "list", name)
    if p.returncode != 0:
        return None
    return parse_ipset_list(p.stdout)


def _create_geo_sets(target: str) -> None:
    subprocess.run(["ipset", "create", f"{target}-site", "hash:ip", "family", "inet",
                    "hashsize", "4096", "maxelem", "131072", "timeout", "3600", "-exist"], check=True)
    subprocess.run(["ipset", "create", f"{target}-ip", "hash:net", "family", "inet",
                    "hashsize", "8192", "maxelem", "262144", "-exist"], check=True)


def convert_reserved_ipset(target: str) -> tuple[bool, str]:
    state = get_ipset_state(target)
    if state is None or state.set_type == "list:set":
        return True, ""
    if state.set_type not in ("hash:ip", "hash:net"):
        return False, f"{target}: unsupported existing ipset type {state.set_type}"
    if state.references != 0:
        return False, (
            f"{target}: existing {state.set_type} has References: {state.references}; "
            "cannot safely replace it while firewall rules reference it"
        )

    _create_geo_sets(target)
    dest = f"{target}-site" if state.set_type == "hash:ip" else f"{target}-ip"
    for member in state.members:
        p = subprocess.run(["ipset", "add", dest, member, "-exist"])
        if p.returncode != 0:
            return False, f"{target}: failed to copy {member} to {dest}"

    if subprocess.run(["ipset", "destroy", target]).returncode != 0:
        return False, f"{target}: failed to destroy existing {state.set_type}"
    if subprocess.run(["ipset", "create", target, "list:set", "-exist"]).returncode != 0:
        return False, f"{target}: failed to create list:set"
    subprocess.run(["ipset", "add", target, f"{target}-site", "-exist"], check=True)
    subprocess.run(["ipset", "add", target, f"{target}-ip", "-exist"], check=True)
    return True, ""


def _prompt_choice(prompt: str, choices: dict[str, str]) -> str:
    options = "/".join(f"{k.upper()}={v}" for k, v in choices.items())
    while True:
        try:
            value = input(f"{prompt} [{options}]: ").strip().lower()
        except EOFError:
            return "s"
        if value in choices:
            return value
        print("Неверный выбор.")


def _backup_once(path: pathlib.Path) -> pathlib.Path:
    backup = path.with_name(path.name + ".geo-route.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def _rewrite_files(
    found: list[FoundDirective],
    per_set_replacements: dict[str, str | None],
) -> None:
    by_path: dict[pathlib.Path, list[FoundDirective]] = defaultdict(list)
    for item in found:
        if any(s in per_set_replacements for s in item.directive.sets):
            by_path[item.path].append(item)

    for path, items in by_path.items():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        item_by_line = {x.line_no: x for x in items}
        out: list[str] = []
        for line_no, line in enumerate(lines, 1):
            item = item_by_line.get(line_no)
            if item is None:
                out.append(line)
                continue
            new_line = rewrite_directive(item.directive, per_set_replacements)
            out.append(new_line)
            changed = changed or new_line != line
        if changed:
            _backup_once(path)
            tmp = path.with_name(path.name + ".geo-route.tmp")
            tmp.write_text("".join(out), encoding="utf-8")
            os.chmod(tmp, path.stat().st_mode)
            os.replace(tmp, path)


def interactive_import(
    dnsmasq_dir: pathlib.Path = DNSMASQ_DIR,
    import_path: pathlib.Path = GEO_IMPORT,
) -> int:
    found = scan_dnsmasq_dir(dnsmasq_dir)
    if not found:
        print("Существующие dnsmasq ipset= правила не найдены.")
        return 0

    grouped: dict[str, set[str]] = defaultdict(set)
    unsupported: list[FoundDirective] = []
    for item in found:
        if not item.directive.supported:
            unsupported.append(item)
            continue
        for s in item.directive.sets:
            grouped[s].update(item.directive.domains)

    if unsupported:
        print("Найдены неподдерживаемые ipset= директивы; они будут оставлены без изменений:")
        for item in unsupported:
            print(f"  {item.path}:{item.line_no}: {item.directive.raw.rstrip()}")

    additions: dict[str, set[str]] = defaultdict(set)
    replacements: dict[str, str | None] = {}

    for source_set in sorted(grouped):
        domains = sorted(grouped[source_set])
        print(f"\nНайден set '{source_set}': {len(domains)} домен(ов)")
        for d in domains[:8]:
            print(f"  {d}")
        if len(domains) > 8:
            print(f"  ... ещё {len(domains) - 8}")

        if source_set in RESERVED_TARGETS:
            target = source_set
        else:
            choice = _prompt_choice(
                f"Куда импортировать '{source_set}'?",
                {"b": "blocked-sites", "r": "only-ru", "s": "не импортировать"},
            )
            if choice == "s":
                continue
            target = "blocked-sites" if choice == "b" else "only-ru"

        action = _prompt_choice(
            f"Что сделать с dnsmasq-привязкой '{source_set}' после импорта?",
            {"k": "оставить", "m": "удалить/перенести", "s": "не переносить"},
        )
        if action == "s":
            continue

        if source_set in RESERVED_TARGETS:
            ok, error = convert_reserved_ipset(source_set)
            if not ok:
                print(f"ОШИБКА: {error}", file=sys.stderr)
                print("Импорт этого set пропущен; исходная конфигурация не изменена.", file=sys.stderr)
                continue

        additions[target].update(domains)
        if action == "m":
            replacements[source_set] = None
        elif source_set in RESERVED_TARGETS:
            # Keep the old dnsmasq rule active, but redirect writes to the
            # hash:ip child because the base set is now list:set.
            replacements[source_set] = f"{target}-site"

    if not additions:
        print("Нечего импортировать.")
        return 0

    merge_import_config(import_path, additions)
    _rewrite_files(found, replacements)
    total = sum(len(v) for v in additions.values())
    print(f"Импортировано доменов: {total}")
    print(f"Конфигурация: {import_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import existing dnsmasq ipset= rules into geo-route")
    parser.add_argument("--yes-skip", action="store_true", help="non-interactive no-op")
    args = parser.parse_args(argv)
    if args.yes_skip:
        return 0
    if not sys.stdin.isatty():
        print("geo-import-dnsmasq: stdin is not a TTY; import skipped")
        return 0
    return interactive_import()


if __name__ == "__main__":
    raise SystemExit(main())
