import os
from pathlib import Path

from apply import DEFAULT_CMD, LOCK, iter_apply


def test_streams_lines_then_exit(tmp_path: Path):
    py = tmp_path / "upd.py"
    py.write_text(
        "import sys\n"
        "print('hello', flush=True)\n"
        "print('world', file=sys.stderr, flush=True)\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    events = list(iter_apply(cmd=["python", str(py)], lock_path=str(tmp_path / "lock")))
    kinds = [e[0] for e in events]
    assert kinds[-1] == "done"
    logs = [e[1] for e in events if e[0] == "log"]
    assert "hello" in logs and "world" in logs
    assert events[-1][1]["exit"] == 3


def test_default_cmd_and_lock():
    assert LOCK == "/opt/var/geo/geo-ui.lock"
    assert DEFAULT_CMD == ["/opt/bin/geo-update", "-n"]


def test_early_close_terminates_subprocess(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    py = tmp_path / "slow.py"
    py.write_text(
        "import os, sys, time\n"
        f"open({pid_file.as_posix()!r}, 'w').write(str(os.getpid()))\n"
        "print('started', flush=True)\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )
    lock_path = str(tmp_path / "lock")
    gen = iter_apply(cmd=["python", str(py)], lock_path=lock_path)
    assert next(gen) == ("log", "started")
    gen.close()

    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        os.kill(pid, 0)
        still_running = True
    except OSError:
        still_running = False
    assert not still_running

    quick = tmp_path / "quick.py"
    quick.write_text("print('ok', flush=True)\n", encoding="utf-8")
    events = list(iter_apply(cmd=["python", str(quick)], lock_path=lock_path))
    assert events[-1] == ("done", {"exit": 0})
    assert "ok" in [e[1] for e in events if e[0] == "log"]
