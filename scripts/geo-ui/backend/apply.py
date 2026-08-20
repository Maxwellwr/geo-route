from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator

LOCK = "/opt/var/geo/geo-ui.lock"
DEFAULT_CMD = ["/opt/bin/geo-update", "-n"]


def iter_apply(
    cmd: list[str] | None = None,
    lock_path: str = LOCK,
) -> Iterator[tuple[str, object]]:
    cmd = cmd or DEFAULT_CMD
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    lockf = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lockf.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert p.stdout is not None
        try:
            for line in p.stdout:
                yield ("log", line.rstrip("\n"))
            code = p.wait()
            p = None
            yield ("done", {"exit": int(code)})
        finally:
            if p is not None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
    finally:
        lockf.close()
