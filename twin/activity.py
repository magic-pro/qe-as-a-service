"""Private, bounded telemetry shared by worktrees of the same local clone."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

RETENTION = timedelta(days=7)
MAX_EVENTS = 6000
ORIGIN = re.compile(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                    r"magic-pro/qe-as-a-service(?:\.git)?/?", re.I)
ID = re.compile(r"[a-zA-Z0-9_-]{1,128}")
KINDS = {
    "copilot": {"session-start", "session-resume", "turn-start", "turn-stop",
                "session-end", "session-error", "subagent-start", "subagent-stop"},
    "qe-manual": {"run-start", "run-exit", "run-failed"},
    "qe-copilot": {"run-start", "run-exit", "run-failed"},
    "qe-webhook": {"run-start", "run-exit", "run-failed"},
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, source TEXT NOT NULL,
    worktree TEXT NOT NULL, run TEXT NOT NULL, child TEXT NOT NULL,
    agent TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY);
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True,
                                   stderr=subprocess.DEVNULL, timeout=1).strip()


def _key(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path.resolve())).hexdigest()[:20]


def scope(cwd: Path) -> tuple[Path, str] | None:
    try:
        root = Path(_git(cwd, "rev-parse", "--show-toplevel"))
        common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        remote = _git(root, "config", "--local", "--get", "remote.origin.url")
    except (OSError, subprocess.SubprocessError):
        return None
    if not ORIGIN.fullmatch(remote):
        return None
    return Path.home() / ".qe-twin" / f"{_key(common)}.sqlite3", _key(root)


def _open(path: Path, write: bool = False) -> sqlite3.Connection:
    if write:
        path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise PermissionError("Twin activity directory must be private")
    if write:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise PermissionError("Twin activity file must be private")
    mode = "rw" if write else "ro"
    return sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=0.25)


def enable_copilot(path: Path, enabled: bool) -> None:
    with closing(_open(path, write=True)) as db, db:
        db.executescript(SCHEMA)
        if enabled:
            db.execute("INSERT OR IGNORE INTO settings VALUES ('copilot')")
        else:
            db.execute("DELETE FROM settings WHERE name = 'copilot'")


def _enabled(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM settings WHERE name = 'copilot'").fetchone() is not None


def record(path: Path, worktree: str, source: str, run: str, kind: str, *,
           child: str = "", agent: str = "", now: datetime | None = None) -> None:
    if kind not in KINDS.get(source, ()):
        raise ValueError("Unknown lifecycle event")
    if any(not isinstance(value, str) or not ID.fullmatch(value)
           for value in (worktree, run, *(v for v in (child, agent) if v))):
        raise ValueError("Invalid lifecycle identifier")
    if source == "copilot" and not path.exists():
        return
    now = now or datetime.now(timezone.utc)
    with closing(_open(path, write=True)) as db, db:
        db.executescript(SCHEMA)
        if source == "copilot":
            db.execute("BEGIN IMMEDIATE")
            if not _enabled(db):
                return
        db.execute("INSERT INTO events (ts, source, worktree, run, child, agent, kind)"
                   " VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (int(now.timestamp() * 1000), source, worktree, run, child, agent, kind))
        db.execute("DELETE FROM events WHERE ts < ? OR seq <= "
                   "(SELECT max(seq) - ? FROM events)",
                   (int((now - RETENTION).timestamp() * 1000), MAX_EVENTS))


def read(path: Path, now: datetime) -> tuple[bool, list[sqlite3.Row]]:
    try:
        with closing(_open(path)) as db:
            db.row_factory = sqlite3.Row
            with db:
                db.execute("BEGIN")
                return _enabled(db), db.execute(
                    "SELECT * FROM events WHERE ts BETWEEN ? AND ? ORDER BY ts, seq",
                    (int((now - RETENTION).timestamp() * 1000), int(now.timestamp() * 1000)),
                ).fetchall()
    except FileNotFoundError:
        return False, []
