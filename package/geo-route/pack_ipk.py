#!/usr/bin/env python3
"""Pack Entware ipk (ar of debian-binary + control.tar.gz + data.tar.gz) and Packages.gz."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import tarfile
import time
from pathlib import Path

EXEC_SUFFIXES = {".sh"}
EXEC_NAMES = {"geo-update", "geo-why", "geoview", "configure.sh", "S80geo-ui", "S05wget-https", "postinst", "prerm"}


def is_exec(path: Path) -> bool:
    if path.name in EXEC_NAMES or path.suffix in EXEC_SUFFIXES:
        return True
    try:
        return bool(path.stat().st_mode & 0o111)
    except OSError:
        return False


def tar_gz(root: Path, files: list[Path] | None = None) -> bytes:
    buf = io.BytesIO()
    mtime = int(time.time())
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        if files is None:
            entries = sorted(p for p in root.rglob("*") if p.is_file())
        else:
            entries = files
        dirs_added: set[str] = set()
        for path in entries:
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            name = "./" + rel
            parent = Path(rel).parent.as_posix()
            if parent not in (".", ""):
                acc: list[str] = []
                for part in parent.split("/"):
                    acc.append(part)
                    d = "/".join(acc)
                    if d not in dirs_added:
                        dinfo = tarfile.TarInfo("./" + d)
                        dinfo.type = tarfile.DIRTYPE
                        dinfo.mode = 0o755
                        dinfo.mtime = mtime
                        tf.addfile(dinfo)
                        dirs_added.add(d)
            info = tarfile.TarInfo(name)
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = mtime
            info.mode = 0o755 if is_exec(path) else 0o644
            info.uid = 0
            info.gid = 0
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def write_ipk(out: Path, debian: bytes, control_tar: bytes, data_tar: bytes) -> None:
    buf = io.BytesIO()
    mtime = int(time.time())
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT) as tf:
        for name, data, mode in (
            ("./debian-binary", debian, 0o644),
            ("./data.tar.gz", data_tar, 0o644),
            ("./control.tar.gz", control_tar, 0o644),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = mtime
            info.mode = mode
            info.uid = 0
            info.gid = 0
            tf.addfile(info, io.BytesIO(data))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())


def parse_control(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if not line:
            continue
        if line[0] in " \t" and key:
            fields[key] += "\n" + line
            continue
        k, _, v = line.partition(":")
        key = k.strip()
        fields[key] = v.strip()
    return fields


def write_packages(control: str, ipk: Path, filename: str, dest: Path) -> None:
    fields = parse_control(control)
    size = ipk.stat().st_size
    raw = ipk.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    md5 = hashlib.md5(raw).hexdigest()
    fields["Filename"] = filename
    fields["Size"] = str(size)
    fields["SHA256sum"] = sha
    fields["MD5Sum"] = md5
    order = [
        "Package",
        "Version",
        "Depends",
        "Section",
        "Architecture",
        "Maintainer",
        "Priority",
        "Installed-Size",
        "Filename",
        "Size",
        "MD5Sum",
        "SHA256sum",
        "Description",
    ]
    lines = []
    seen = set()
    for k in order:
        if k in fields:
            lines.append(f"{k}: {fields[k]}")
            seen.add(k)
    for k, v in fields.items():
        if k not in seen:
            lines.append(f"{k}: {v}")
    body = "\n".join(lines) + "\n\n"
    dest.write_text(body, encoding="utf-8", newline="\n")
    with gzip.open(dest.with_name("Packages.gz"), "wb") as gz:
        gz.write(body.encode("utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--ipk", type=Path, required=True)
    p.add_argument("--feed", type=Path, required=True)
    p.add_argument("--filename", required=True)
    args = p.parse_args()

    control_files = [
        args.control / "control",
        args.control / "conffiles",
        args.control / "postinst",
        args.control / "prerm",
    ]
    control_tar = tar_gz(args.control, control_files)
    data_tar = tar_gz(args.stage)
    debian = b"2.0\n"
    write_ipk(args.ipk, debian, control_tar, data_tar)
    args.feed.mkdir(parents=True, exist_ok=True)
    dest_ipk = args.feed / args.filename
    dest_ipk.write_bytes(args.ipk.read_bytes())
    (args.feed.parent / ".nojekyll").write_text("", encoding="utf-8")
    write_packages(
        (args.control / "control").read_text(encoding="utf-8"),
        dest_ipk,
        args.filename,
        args.feed / "Packages",
    )


if __name__ == "__main__":
    main()
