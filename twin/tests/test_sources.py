"""Tests for the agent twin data sources."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twin import sources as s

NOW = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)


def ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_repo(root: Path) -> None:
    write(root / ".claude/agents/builder-agent.md",
          "---\nname: builder-agent\ntype: Agent\ntitle: Builder\ndescription: Builds tests\n---\nbody\n")
    write(root / ".claude/agents/qe-analysis-agent.md",
          "---\nname: qe-analysis-agent\ntype: Agent\ntitle: Analyst\ndescription: Story maps\n---\nbody\n")
    write(root / ".claude/agents/planning-agent.md",
          "---\nname: planning-agent\ntype: Agent\ntitle: Planner\ndescription: Plans\n---\nbody\n")


def make_session(state: Path, sid: str, events: list, workspace: str = "") -> Path:
    d = state / sid
    write(d / "events.jsonl", "\n".join(json.dumps(e) for e in events) + "\n")
    if workspace:
        write(d / "workspace.yaml", workspace)
    return d


def start(minutes_ago: float, repo: str = "me/qe-as-a-service") -> dict:
    return {"type": "session.start", "timestamp": ts(minutes_ago),
            "data": {"context": {"repository": repo, "cwd": "/x/" + repo.split("/")[-1], "branch": "main"}}}


class JournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        make_repo(self.tmp)
        self.journal = self.tmp / "activity.jsonl"

    def lanes(self, now: datetime = NOW) -> dict:
        snap = s.snapshot(self.tmp, copilot_dir=self.tmp / "none", journal=self.journal, now=now)
        return {lane["id"]: lane for lane in snap["lanes"]}

    def test_dispatched_is_working_then_idles_after_ttl(self) -> None:
        s.record_activity("builder-agent", "dispatched", "Build tests for PROJ-1",
                          path=self.journal, ts=NOW - timedelta(minutes=5))
        self.assertEqual(self.lanes()["builder-agent"]["status"], "working")
        later = NOW + s.RUN_TTL
        self.assertEqual(self.lanes(later)["builder-agent"]["status"], "idle")

    def test_done_fades_to_idle(self) -> None:
        s.record_activity("planning-agent", "done", "Story map written",
                          path=self.journal, ts=NOW - timedelta(minutes=2))
        self.assertEqual(self.lanes()["planning-agent"]["status"], "done")
        self.assertEqual(self.lanes(NOW + s.DONE_TTL)["planning-agent"]["status"], "idle")

    def test_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValueError):
            s.record_activity("builder-agent", "sleeping", path=self.journal)

    def test_pending_review_story_map_waits_for_human(self) -> None:
        write(self.tmp / "knowledge/findings/2025-01-15-story-map.md",
              f"---\ntype: Story Map\ntitle: Checkout\nstatus: pending-review\ntimestamp: {ts(10)}\n---\n")
        lanes = self.lanes()
        self.assertEqual(lanes["qe-analysis-agent"]["status"], "waiting")

    def test_initial_seeds_replay_before_window(self) -> None:
        s.record_activity("builder-agent", "done", "old run", path=self.journal, ts=NOW - timedelta(hours=30))
        s.record_activity("builder-agent", "working", "new run", path=self.journal, ts=NOW - timedelta(hours=1))
        snap = s.snapshot(self.tmp, copilot_dir=self.tmp / "none", journal=self.journal, now=NOW, hours=24)
        self.assertEqual(snap["initial"]["builder-agent"]["label"], "old run")
        self.assertEqual([e["label"] for e in snap["timeline"] if e["lane"] == "builder-agent"], ["new run"])


class CopilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        s._CACHE.entries.clear()

    def status(self, events: list, workspace: str = "", now: datetime = NOW) -> dict:
        d = make_session(self.tmp, "sess-1", events, workspace)
        parsed = s.parse_copilot_session(d)
        lane = s.lane_status(parsed["timeline"], now, kind="copilot")
        return {**parsed, **lane}

    def test_open_turn_is_working(self) -> None:
        lane = self.status([start(5), {"type": "user.message", "timestamp": ts(4), "data": {}},
                            {"type": "tool.execution_start", "timestamp": ts(3),
                             "data": {"toolName": "bash", "toolCallId": "a",
                                      "arguments": {"description": "Run tests", "command": "secret"}}}])
        self.assertEqual(lane["status"], "working")
        self.assertNotIn("secret", json.dumps(lane["timeline"]))

    def test_shutdown_is_ended(self) -> None:
        lane = self.status([start(5), {"type": "session.shutdown", "timestamp": ts(1), "data": {}}])
        self.assertEqual(lane["status"], "ended")

    def test_ask_user_waits(self) -> None:
        lane = self.status([start(5), {"type": "assistant.turn_start", "timestamp": ts(4), "data": {}},
                            {"type": "tool.execution_start", "timestamp": ts(3),
                             "data": {"toolName": "ask_user", "toolCallId": "q"}}])
        self.assertEqual(lane["status"], "waiting")

    def test_quick_permission_is_not_a_wait(self) -> None:
        lane = self.status([start(5), {"type": "assistant.turn_start", "timestamp": ts(4), "data": {}},
                            {"type": "permission.requested", "timestamp": ts(3), "data": {"requestId": "p"}},
                            {"type": "permission.completed", "timestamp": ts(3), "data": {"requestId": "p"}}])
        self.assertFalse(any(e["status"] == "waiting" for e in lane["timeline"]))

    def test_slow_and_pending_permissions_wait(self) -> None:
        lane = self.status([start(10), {"type": "assistant.turn_start", "timestamp": ts(9), "data": {}},
                            {"type": "permission.requested", "timestamp": ts(8), "data": {"requestId": "p"}},
                            {"type": "permission.completed", "timestamp": ts(6), "data": {"requestId": "p"}},
                            {"type": "permission.requested", "timestamp": ts(2), "data": {"requestId": "q"}}])
        waits = [e for e in lane["timeline"] if e["status"] == "waiting"]
        self.assertEqual(len(waits), 2)
        self.assertEqual(lane["status"], "waiting")

    def test_block_scalar_workspace_name(self) -> None:
        lane = self.status([start(5)], workspace="name: |-\n  QE agent twin\ncwd: /x\n")
        self.assertEqual(lane["name"], "QE agent twin")

    def test_stale_sessions_go_idle_and_filter_by_repo(self) -> None:
        make_session(self.tmp, "stale", [start(120), {"type": "user.message", "timestamp": ts(119), "data": {}}])
        make_session(self.tmp, "other", [start(5, repo="me/elsewhere"),
                                         {"type": "user.message", "timestamp": ts(4), "data": {}}])
        sessions = s.copilot_sessions(self.tmp, match="qe-as-a-service", now=NOW, window=timedelta(days=36500))
        self.assertEqual([x["id"] for x in sessions], ["stale"])
        self.assertEqual(sessions[0]["status"], "idle")
        self.assertEqual(sessions[0]["activity"], "Inactive")


if __name__ == "__main__":
    unittest.main()
