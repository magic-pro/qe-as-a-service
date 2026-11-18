"""Observe local Claude Code processes without changing their tool permissions."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4

from twin import activity


def launch(agent: str, source: str, command: list[str], *,
           cwd: Path, background: bool = False, **kwargs) -> int | None:
    scoped = activity.scope(cwd)
    run = uuid4().hex

    def emit(kind: str) -> None:
        if scoped:
            try:
                activity.record(*scoped, source, run, kind, agent=agent)
            except (OSError, sqlite3.Error, ValueError) as exc:
                logging.warning("QE Twin could not record %s (%s)", kind, type(exc).__name__)

    try:
        process = subprocess.Popen(command, cwd=cwd, **kwargs)
    except OSError:
        emit("run-failed")
        raise
    emit("run-start")

    def wait() -> int:
        code = process.wait()
        emit("run-exit" if code == 0 else "run-failed")
        return code if code >= 0 else 128 - code

    if not background:
        return wait()
    if scoped:
        from threading import Thread

        Thread(target=wait, daemon=True).start()
    return None
