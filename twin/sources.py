"""Build the studio timeline from observed lifecycle events and local QE evidence."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from twin import activity

REPO_ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER = timedelta(minutes=30)
LIFECYCLE = {
    "session-start": ("idle", "Session opened"),
    "session-resume": ("idle", "Session resumed"),
    "turn-start": ("working", "Turn or tool activity observed"),
    "turn-stop": ("idle", "Turn ended"),
    "session-end": ("ended", "Session closed"),
    "session-error": ("unknown", "Session reported an error"),
    "subagent-start": ("working", "Subagent started"),
    "subagent-stop": ("ended", "Subagent stopped"),
    "run-start": ("working", "Claude Code process started"),
    "run-exit": ("done", "Claude Code exited successfully"),
    "run-failed": ("failed", "Claude Code failed to start or exited unsuccessfully"),
}

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
                label = f"Signal recorded: {doc_type}"
            else:
                lane = DOC_TYPE_AGENT.get(doc_type)
                if not lane and path.name.endswith("-story-map.md"):
                    lane = "qe-analysis-agent"
                if not lane and path.name.endswith("-build-report.md"):
                    lane = "builder-agent"
                if not lane:
                    continue
                status = "waiting" if meta.get("status") == "pending-review" else "unknown"
                verb = "Awaiting human review" if status == "waiting" else "Artifact recorded"
                label = f"{verb}: {doc_type or 'QE artifact'}"
            ts = parse_ts(meta.get("timestamp"))
            if ts is None:
                try:
                    ts = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                except OSError:
                    continue
            ev = _event(ts, lane, status, label, "okf")
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
                yield _event(ts, who, "unknown", "Activity noted in change log", "log.md")


def lane_status(last: dict | None, now: datetime) -> dict[str, Any]:
    if not last:
        return {"status": "unknown", "activity": "No activity observed", "since": None}
    expires = last.get("expires")
    if expires and now >= parse_ts(expires):
        return {"status": "unknown", "activity": "No recent lifecycle update",
                "since": last["ts"]}
    return {"status": last["status"], "activity": last["label"], "since": last["ts"]}


# ---------------------------------------------------------------- snapshot

def snapshot(root: Path = REPO_ROOT, *, hours: int = 24,
             journal: Optional[Path] = None,
             now: Optional[datetime] = None) -> dict[str, Any]:
    """Everything the twin UI needs: lanes with live status plus a replay timeline."""
    now = now or now_utc()
    window_start = now - timedelta(hours=hours)
    agents = discover_qe_agents(root)
    names = {agent["id"]: agent["name"] for agent in agents}
    events = [*(e for e in _doc_events(root) if e["lane"] in names),
              *_log_line_events(root, set(names))]
    if journal is None:
        scoped = activity.scope(root)
        journal = scoped[0] if scoped else None
    health = {"copilot": "disabled", "qe": "unobserved"}
    rows = []
    if journal:
        try:
            enabled, rows = activity.read(journal, now)
            health["copilot"] = "unobserved" if enabled else "disabled"
        except (OSError, sqlite3.Error):
            health = {"copilot": "unavailable", "qe": "unavailable"}
    else:
        health = {"copilot": "unavailable", "qe": "unavailable"}

    runtime = {}
    delegated = {(row["worktree"], row["child"]) for row in rows
                 if row["source"] == "copilot" and row["child"]}
    for row in rows:
        source, worktree, run, child = (row[k] for k in ("source", "worktree", "run", "child"))
        copilot = source == "copilot"
        # A delegated agent can also emit its own turn hooks under its child ID.
        if copilot and not child and (worktree, run) in delegated:
            continue
        health["copilot" if copilot else "qe"] = (
            "disabled" if copilot and not enabled else "observed"
        )
        lane = ":".join((source, worktree, run, child))
        title = ("Subagent " + child[:8] if child else "Session " + run[:8]) if copilot else (
            names.get(row["agent"], row["agent"]) + " · " + run[:8])
        runtime[lane] = {"id": lane, "kind": "copilot" if copilot else "qe",
                         "name": title, "scope": source, "worktree": worktree,
                         "parent": ":".join((source, worktree, run, "")) if child else None}
        ts = parse_ts(row["ts"])
        status, label = LIFECYCLE[row["kind"]]
        event = _event(ts, lane, status, label, source)
        if status == "working" or (copilot and status == "idle"):
            event["expires"] = iso(ts + STALE_AFTER)
        events.append(event)

    initial, timeline, latest = {}, [], {}
    window_iso, now_iso = iso(window_start), iso(now)
    events.sort(key=lambda event: parse_ts(event["ts"]))
    for event in events:
        ts = parse_ts(event["ts"])
        if ts > now:
            continue
        lane = event["lane"]
        latest[lane] = event
        if ts < window_start:
            initial[lane] = event
        else:
            timeline.append(event)
    current_runs = sorted(
        (lane for lane in runtime if parse_ts(latest[lane]["ts"]) >= window_start),
        key=lambda lane: (lane_status(latest[lane], now)["status"] == "working",
                          parse_ts(latest[lane]["ts"])),
        reverse=True,
    )
    # Keep run studios bounded without dropping the per-run history for displayed studios.
    visible = set(current_runs[:24]) | set(names)
    lanes = [{**lane, **lane_status(latest.get(lane["id"]), now)}
             for lane in [*agents, *(runtime[i] for i in current_runs[:24])]]
    return {
        "generatedAt": now_iso,
        "windowStart": window_iso,
        "lanes": lanes,
        "sources": health,
        "timeline": [e for e in timeline if e["lane"] in visible],
        "initial": {i: event for i, event in initial.items() if i in visible},
    }
