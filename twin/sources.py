"""Collect live agent state for the QEaaS agent twin.

Two kinds of lane feed the twin:

* QE agents — one studio per `.claude/agents/*.md` definition (plus the in-repo
  Test Creator / Test Healer from `repo-templates/`). Activity comes from the
  agent activity journal, OKF findings/signals and `log.md` change lines.
* Copilot sessions — one studio per GitHub Copilot session, read from the
  session `events.jsonl` files under `~/.copilot/session-state/`.

Everything here is read-only apart from `record_activity`, and uses only the
standard library so the twin runs without installing anything.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

ACTIVITY_LOG = Path(os.environ.get("QE_TWIN_ACTIVITY_LOG", REPO_ROOT / "knowledge" / "agent-activity.jsonl"))
COPILOT_STATE_DIR = Path(
    os.environ.get("QE_TWIN_COPILOT_DIR", Path.home() / ".copilot" / "session-state")
)

# A dispatched QE agent run with no further report is assumed finished after this.
RUN_TTL = timedelta(minutes=int(os.environ.get("QE_TWIN_RUN_TTL_MINUTES", "30")))
# How long a finished run keeps its "done"/"failed" badge before going idle.
DONE_TTL = timedelta(minutes=10)
# A Copilot session with no events for this long is shown idle even mid-turn.
COPILOT_STALE = timedelta(minutes=30)
# A session blocked on a prompt for this long is treated as abandoned.
COPILOT_WAIT_STALE = timedelta(hours=4)
COPILOT_TAIL_BYTES = 1_000_000
# Permission prompts resolved faster than this were auto-approved; don't show them as waiting.
PERMISSION_WAIT = timedelta(seconds=5)

STATUSES = ("working", "waiting", "done", "failed", "idle", "ended")
JOURNAL_STATUSES = {"dispatched": "working", "working": "working", "waiting": "waiting",
                    "done": "done", "failed": "failed", "idle": "idle"}

# OKF doc type → QE agent that produces it.
DOC_TYPE_AGENT = {
    "Story Map": "qe-analysis-agent",
    "Build Report": "builder-agent",
    "Coverage Gap": "coverage-agent",
    "Incident RCA": "incident-agent",
    "Regression Test Request": "incident-agent",
    "Map Update": "planning-agent",
    "Test Strategy": "planning-agent",
    "Infra Map": "planning-agent",
    "Data Type Map": "planning-agent",
    "Identity Map": "planning-agent",
    "Domain Map": "planning-agent",
}
SIGNAL_TYPES = {"Jira Story", "Jira Bug", "Jira Epic", "GitHub CI Failure",
                "GitHub Pull Request", "GCP Log Pattern"}
SIGNAL_LANE = "signal-inbox"

KNOWLEDGE_DIRS = ("knowledge", "docs/knowledge", "artifacts", "e2e/runs")
LOG_DIRS = ("knowledge", "repo-templates", "e2e")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"}
LOG_LINE = re.compile(r"^-\s+(\S+)\s+·\s+([^·]+?)\s+·\s+(.+?)(?:\s+·\s+derived_from\s+(.+))?\s*$")


# ---------------------------------------------------------------- helpers

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
    text = str(value).strip().strip("'\"")
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python 3.9's fromisoformat only accepts 3 or 6 fractional digits.
    text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        try:
            ts = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def short(text: Any, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def read_frontmatter(path: Path) -> dict[str, str]:
    """Top-level scalar keys of a YAML frontmatter block (no PyYAML needed)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            if fh.readline().rstrip("\n") != "---":
                return {}
            meta: dict[str, str] = {}
            for _ in range(200):
                line = fh.readline()
                if not line or line.rstrip("\n") == "---":
                    break
                if line[:1].isspace() or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                meta[key.strip()] = value
            return meta
    except OSError:
        return {}


def _event(ts: datetime, lane: str, status: str, label: str, source: str) -> dict[str, Any]:
    return {"ts": iso(ts), "lane": lane, "status": status, "label": short(label), "source": source}


# ---------------------------------------------------------------- QE agents

def discover_qe_agents(root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    agents: dict[str, dict[str, Any]] = {}
    for scope, pattern in (("qe-as-a-service", ".claude/agents/*.md"),
                           ("target repos", "repo-templates/*/.claude/agents/*.md")):
        for path in sorted(root.glob(pattern)):
            meta = read_frontmatter(path)
            name = meta.get("name") or path.stem
            if name in agents:
                continue
            agents[name] = {
                "id": name,
                "kind": "qe",
                "name": meta.get("title") or name.replace("-", " ").title(),
                "description": short(meta.get("description", ""), 160),
                "scope": scope,
            }
    agents[SIGNAL_LANE] = {
        "id": SIGNAL_LANE,
        "kind": "qe",
        "name": "Signal Inbox",
        "description": "Jira, GitHub and GCP events normalised into OKF signal docs by webhooks/receiver.py.",
        "scope": "webhooks",
    }
    return list(agents.values())


def record_activity(agent: str, status: str, message: str = "", *, source: str = "agent",
                    path: Optional[Path] = None, ts: Optional[datetime] = None) -> dict[str, Any]:
    """Append one line to the agent activity journal. Agents and the webhook receiver call this."""
    if status not in JOURNAL_STATUSES:
        raise ValueError(f"status must be one of {sorted(JOURNAL_STATUSES)}")
    entry = {"ts": iso(ts or now_utc()), "agent": agent, "status": status,
             "message": short(message, 200), "source": source}
    path = path or ACTIVITY_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def _journal_events(path: Path) -> Iterable[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        ts = parse_ts(entry.get("ts"))
        agent = entry.get("agent")
        status = JOURNAL_STATUSES.get(entry.get("status", ""))
        if ts and agent and status:
            label = entry.get("message") or entry.get("status")
            yield _event(ts, agent, status, label, "journal")


def _walk(root: Path, sub: str, name_filter) -> Iterable[Path]:
    base = root / sub
    if not base.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if name_filter(fn):
                yield Path(dirpath) / fn


def _doc_events(root: Path) -> Iterable[dict[str, Any]]:
    seen: set = set()
    for sub in KNOWLEDGE_DIRS:
        for path in _walk(root, sub, lambda fn: fn.endswith(".md") and fn not in ("index.md", "log.md")):
            if path in seen:
                continue
            seen.add(path)
            meta = read_frontmatter(path)
            doc_type = meta.get("type", "")
            if meta.get("status") == "template":
                continue
            if doc_type in SIGNAL_TYPES:
                lane, status = SIGNAL_LANE, "done"
                label = f"{doc_type}: {meta.get('key') or meta.get('title') or path.stem}"
            else:
                lane = DOC_TYPE_AGENT.get(doc_type)
                if not lane and path.name.endswith("-story-map.md"):
                    lane = "qe-analysis-agent"
                if not lane and path.name.endswith("-build-report.md"):
                    lane = "builder-agent"
                if not lane:
                    continue
                status = "waiting" if meta.get("status") == "pending-review" else "done"
                verb = "Awaiting human review" if status == "waiting" else "Wrote"
                label = f"{verb}: {meta.get('title') or path.name}"
            ts = parse_ts(meta.get("timestamp"))
            if ts is None:
                try:
                    ts = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                except OSError:
                    continue
            ev = _event(ts, lane, status, label, "okf")
            ev["path"] = str(path.relative_to(root))
            yield ev


def _log_line_events(root: Path, agent_ids: set) -> Iterable[dict[str, Any]]:
    paths = [root / "log.md"]
    for sub in LOG_DIRS:
        paths += list(_walk(root, sub, lambda fn: fn == "log.md"))
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            m = LOG_LINE.match(line.strip())
            if not m:
                continue
            ts, who = parse_ts(m.group(1)), m.group(2).strip()
            if ts and who in agent_ids:
                ev = _event(ts, who, "done", m.group(3), "log.md")
                ev["path"] = str(path.relative_to(root))
                yield ev


def qe_events(root: Path = REPO_ROOT, journal: Optional[Path] = None,
              agent_ids: Optional[set] = None) -> list[dict[str, Any]]:
    if agent_ids is None:
        agent_ids = {a["id"] for a in discover_qe_agents(root)}
    events = list(_journal_events(journal or ACTIVITY_LOG))
    events += _doc_events(root)
    events += _log_line_events(root, agent_ids)
    events.sort(key=lambda e: e["ts"])
    return events


def lane_status(events: list, now: datetime, kind: str = "qe") -> dict[str, Any]:
    """Current status of one lane from its time-ordered events."""
    if not events:
        return {"status": "idle", "activity": "No activity yet", "since": None}
    last = events[-1]
    ts = parse_ts(last["ts"]) or now
    status = last["status"]
    age = now - ts
    if kind == "qe":
        if status == "working" and age > RUN_TTL:
            status = "idle"
        elif status in ("done", "failed") and age > DONE_TTL:
            status = "idle"
    return {"status": status, "activity": last["label"], "since": last["ts"]}


# ---------------------------------------------------------------- Copilot sessions

class _CopilotCache:
    """Re-parse a session only when its events.jsonl changes."""

    def __init__(self) -> None:
        self.entries: dict = {}

    def get(self, path: Path) -> Optional[dict[str, Any]]:
        try:
            st = path.stat()
        except OSError:
            return None
        key = (st.st_mtime, st.st_size)
        hit = self.entries.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
        parsed = parse_copilot_session(path.parent)
        self.entries[str(path)] = (key, parsed)
        return parsed


_CACHE = _CopilotCache()


def _read_workspace_yaml(session_dir: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        lines = (session_dir / "workspace.yaml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return meta
    for i, line in enumerate(lines):
        if ":" not in line or line[:1].isspace():
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v in ("|", "|-", "|+", ">", ">-", ">+"):
            # Block scalar: use its first non-empty line.
            v = next((ln.strip() for ln in lines[i + 1:] if ln.strip()), "")
        meta[k.strip()] = v.strip("'\"")
    return meta


def _read_jsonl(path: Path, tail_bytes: int) -> tuple:
    """First event (session.start) plus every complete event in the file tail."""
    try:
        with path.open("rb") as fh:
            head = fh.readline()
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - tail_bytes)
            fh.seek(start)
            chunk = fh.read()
    except OSError:
        return None, []
    try:
        first = json.loads(head)
    except ValueError:
        first = None
    lines = chunk.split(b"\n")
    if start > 0:
        lines = lines[1:]  # first line of the tail is partial
    events = []
    for raw in lines:
        if raw.strip():
            try:
                events.append(json.loads(raw))
            except ValueError:
                continue
    return first, events


def _tool_label(data: dict) -> str:
    name = data.get("toolName") or "tool"
    args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
    desc = args.get("description") or args.get("intent") or ""
    return f"{name}: {desc}" if desc else name


def parse_copilot_session(session_dir: Path, tail_bytes: int = COPILOT_TAIL_BYTES) -> dict[str, Any]:
    ws = _read_workspace_yaml(session_dir)
    first, events = _read_jsonl(session_dir / "events.jsonl", tail_bytes)
    context: dict[str, Any] = {}
    if first and first.get("type") == "session.start":
        context = dict(first.get("data", {}).get("context") or {})

    lane = session_dir.name
    timeline: list = []
    open_turn = ended = False
    pending_perms: dict = {}
    running_tools: dict = {}
    waiting_tools: set = set()
    last_ts: Optional[datetime] = None
    model = None

    def status() -> str:
        if ended:
            return "ended"
        if waiting_tools:
            return "waiting"
        if open_turn or running_tools:
            return "working"
        return "idle"

    for ev in events:
        et = ev.get("type", "")
        data = ev.get("data") or {}
        ts = parse_ts(ev.get("timestamp"))
        if ts is None:
            continue
        last_ts = ts
        label = None
        if et in ("session.start", "session.resume"):
            ended = False
            context.update(data.get("context") or {})
            model = data.get("selectedModel") or model
            label = "Session resumed" if et == "session.resume" else "Session started"
        elif et == "session.shutdown":
            ended, open_turn = True, False
            pending_perms.clear(); running_tools.clear(); waiting_tools.clear()
            label = "Session ended"
        elif et == "session.model_change":
            model = data.get("newModel") or model
        elif et == "user.message":
            open_turn = True
            label = "New request"
        elif et == "assistant.turn_start":
            open_turn = True
            label = "Thinking"
        elif et == "assistant.turn_end":
            open_turn = False
            running_tools.clear(); waiting_tools.clear()
            label = "Turn finished"
        elif et == "tool.execution_start":
            call = data.get("toolCallId", "")
            running_tools[call] = label = _tool_label(data)
            if data.get("toolName") in ("ask_user", "relay_session_input"):
                waiting_tools.add(call)
                label = "Waiting for your answer"
        elif et == "tool.execution_complete":
            running_tools.pop(data.get("toolCallId", ""), None)
            if data.get("toolCallId", "") in waiting_tools:
                waiting_tools.discard(data.get("toolCallId", ""))
                label = "Got your answer"
        elif et == "permission.requested":
            pending_perms[data.get("requestId", "")] = ts
        elif et == "permission.completed":
            asked = pending_perms.pop(data.get("requestId", ""), None)
            if asked and ts - asked > PERMISSION_WAIT and not ended:
                timeline.append(_event(asked, lane, "waiting", "Waiting for permission", "copilot"))
                label = "Permission resolved"
        elif et == "subagent.started":
            label = f"Delegated to {data.get('agentDisplayName') or data.get('agentName') or 'subagent'}"
        elif et == "subagent.completed":
            label = f"{data.get('agentDisplayName') or data.get('agentName') or 'Subagent'} finished"
        if label is not None:
            timeline.append(_event(ts, lane, status(), label, "copilot"))

    timeline.sort(key=lambda e: e["ts"])
    # Permission prompts still open when the log ends: the session is blocked on you.
    if pending_perms and not ended:
        asked = max(pending_perms.values())
        if timeline:
            asked = max(asked, parse_ts(timeline[-1]["ts"]) or asked)
        timeline.append(_event(asked, lane, "waiting", "Waiting for permission", "copilot"))

    repo = context.get("repository") or ""
    cwd = context.get("cwd") or ws.get("cwd") or ""
    title = ws.get("name") or (repo.split("/")[-1] if repo else Path(cwd).name) or lane[:8]
    return {
        "id": lane,
        "kind": "copilot",
        "name": short(title, 40),
        "description": short(" · ".join(x for x in (repo, context.get("branch")) if x) or cwd, 120),
        "repository": repo,
        "cwd": cwd,
        "model": model,
        "lastEvent": iso(last_ts) if last_ts else None,
        "timeline": timeline,
    }


def copilot_sessions(state_dir: Path = COPILOT_STATE_DIR, *, window: timedelta = timedelta(hours=24),
                     match: Optional[str] = None, limit: int = 12,
                     now: Optional[datetime] = None) -> list:
    """Recently active Copilot sessions, optionally filtered by a repo/cwd/name substring."""
    now = now or now_utc()
    if not state_dir.is_dir():
        return []
    candidates = []
    for events_file in state_dir.glob("*/events.jsonl"):
        try:
            mtime = datetime.fromtimestamp(events_file.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if now - mtime <= window:
            candidates.append((mtime, events_file))
    candidates.sort(reverse=True)
    needle = match.lower() if match else None
    sessions = []
    for _, events_file in candidates:
        parsed = _CACHE.get(events_file)
        if not parsed or not parsed["timeline"]:
            continue
        if needle and needle not in f"{parsed['repository']} {parsed['cwd']} {parsed['name']}".lower():
            continue
        s = dict(parsed)
        s.update(lane_status(s["timeline"], now, kind="copilot"))
        last = parse_ts(s["lastEvent"])
        if last and ((s["status"] == "working" and now - last > COPILOT_STALE)
                     or (s["status"] == "waiting" and now - last > COPILOT_WAIT_STALE)):
            s["status"] = "idle"
            s["activity"] = "Inactive"
        sessions.append(s)
        if len(sessions) >= limit:
            break
    return sessions


# ---------------------------------------------------------------- snapshot

def snapshot(root: Path = REPO_ROOT, *, copilot_dir: Path = COPILOT_STATE_DIR,
             copilot_match: Optional[str] = None, copilot_limit: int = 12,
             hours: int = 24, journal: Optional[Path] = None,
             now: Optional[datetime] = None) -> dict[str, Any]:
    """Everything the twin UI needs: lanes with live status plus a replay timeline."""
    now = now or now_utc()
    window_start = now - timedelta(hours=hours)
    agents = discover_qe_agents(root)
    events = qe_events(root, journal, {a["id"] for a in agents})
    by_lane: dict = {}
    for ev in events:
        by_lane.setdefault(ev["lane"], []).append(ev)

    lanes = []
    for agent in agents:
        lane = dict(agent)
        lane.update(lane_status(by_lane.get(agent["id"], []), now))
        lanes.append(lane)

    timeline = [e for e in events if parse_ts(e["ts"]) >= window_start]
    initial = {}
    for lane_id, evs in by_lane.items():
        before = [e for e in evs if parse_ts(e["ts"]) < window_start]
        if before:
            initial[lane_id] = before[-1]

    for s in copilot_sessions(copilot_dir, window=timedelta(hours=hours), match=copilot_match,
                              limit=copilot_limit, now=now):
        lane_events = s.pop("timeline")
        timeline += [e for e in lane_events if parse_ts(e["ts"]) >= window_start]
        before = [e for e in lane_events if parse_ts(e["ts"]) < window_start]
        if before:
            initial[s["id"]] = before[-1]
        lanes.append(s)
    timeline.sort(key=lambda e: e["ts"])

    counts = {s: 0 for s in STATUSES}
    for lane in lanes:
        counts[lane["status"]] = counts.get(lane["status"], 0) + 1
    return {
        "generatedAt": iso(now),
        "windowStart": iso(window_start),
        "lanes": lanes,
        "counts": counts,
        "timeline": timeline[-3000:],
        "initial": initial,
    }
