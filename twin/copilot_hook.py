"""Translate documented Copilot hook input without persisting payload content."""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

from twin import activity

HOOKS = {
    "SessionStart": "session-start",
    "SessionEnd": "session-end",
    "UserPromptSubmit": "turn-start",
    "PreToolUse": "turn-start",
    "Stop": "turn-stop",
    "ErrorOccurred": "session-error",
    "SubagentStart": "subagent-start",
    "SubagentStop": "subagent-stop",
}


def capture(event: str, payload: dict) -> None:
    kind = HOOKS[event]
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError("Missing or invalid hook working directory")
    scoped = activity.scope(Path(cwd))
    if scoped is None or not scoped[0].exists():
        return
    session = payload.get("session_id") or payload.get("sessionId")
    if not isinstance(session, str) or not session:
        raise ValueError("Hook payload lacks a session ID")
    child = ""
    if kind.startswith("subagent-"):
        child = payload.get("agent_id") or payload.get("agentId")
        if not isinstance(child, str) or not child:
            raise ValueError("Hook payload lacks a child agent ID")
    if kind == "session-start" and payload.get("source") == "resume":
        kind = "session-resume"
    activity.record(*scoped, "copilot", session, kind, child=child)


def main() -> None:
    try:
        limit = 10 * 1024 * 1024
        raw = sys.stdin.buffer.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Hook payload exceeded limit")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid hook payload")
        capture(sys.argv[1], data)
    except (OSError, sqlite3.Error, ValueError, KeyError, RecursionError) as exc:
        logging.warning("QE Twin did not capture Copilot activity (%s)", type(exc).__name__)


if __name__ == "__main__":
    main()
