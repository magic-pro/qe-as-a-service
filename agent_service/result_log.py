"""Write private, best-effort redacted agent result records."""

import fcntl
import os
import re
import stat
from pathlib import Path

from okf.normalize import redact

from agent_service.contracts import AgentResult

_TOKEN = re.compile(
    r"\b(?:github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9_]+|"
    r"sk-[A-Za-z0-9_-]+)\b"
)


def _redact(value: str | None) -> str | None:
    return _TOKEN.sub("<credential>", redact(value)) if value is not None else None


def write_result(result: AgentResult) -> None:
    directory = Path(os.environ.get("QE_AGENT_LOG_DIR", str(Path.home() / ".qe-agent-service")))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise PermissionError("Agent log directory must be private")
    path = directory / "agent-results.jsonl"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise PermissionError("Agent log file must be private")
        safe = result.model_copy(update={"output": _redact(result.output), "error": _redact(result.error)})
        data = (safe.model_dump_json() + "\n").encode("utf-8")
        with os.fdopen(fd, "ab") as stream:
            fd = -1
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(data)
    finally:
        if fd != -1:
            os.close(fd)
