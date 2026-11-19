"""Verify the journal-to-studio contract, without requiring agent credentials."""

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from io import StringIO
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from twin import activity, copilot_hook, qe_run, server, sources
from twin.__main__ import main

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


class TwinTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.journal = self.root / "private" / "test.sqlite3"

    def test_only_opted_in_hook_metadata_reaches_the_studios(self):
        with patch.object(activity, "scope", return_value=(self.journal, "worktree")):
            data = {"cwd": str(self.root), "session_id": "session-1",
                    "prompt": "private-prompt", "toolArgs": {"token": "private-token"}}
            copilot_hook.capture("UserPromptSubmit", data)
            self.assertFalse(self.journal.exists())
            activity.enable_copilot(self.journal, True)
            copilot_hook.capture("UserPromptSubmit", data)
            copilot_hook.capture("SubagentStart", {**data, "agent_id": "child-1"})
            copilot_hook.capture("UserPromptSubmit", {**data, "session_id": "child-1"})
            copilot_hook.capture("SubagentStop", {**data, "agentId": "child-1"})
            activity.enable_copilot(self.journal, False)
            copilot_hook.capture("Stop", data)
        state = sources.snapshot(self.root, journal=self.journal)
        child = next(lane for lane in state["lanes"] if lane.get("parent"))
        self.assertEqual(child["status"], "ended")
        self.assertEqual(len([lane for lane in state["lanes"] if lane["kind"] == "copilot"]), 2)
        self.assertEqual(state["sources"]["copilot"], "disabled")
        self.assertEqual(len(state["timeline"]), 3)
        self.assertNotIn(b"private-", self.journal.read_bytes())

    def test_scope_accepts_worktrees_but_not_lookalike_origins(self):
        repo = self.root / "repo"
        repo.mkdir()

        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        git("init")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "Init")
        git("remote", "add", "origin", "git@github.com:magic-pro/qe-as-a-service.git")
        another = self.root / "worktree"
        git("worktree", "add", "--detach", str(another), "HEAD")
        path, key = activity.scope(repo)
        other_path, other_key = activity.scope(another)
        self.assertEqual(path, other_path)
        self.assertNotEqual(key, other_key)
        git("remote", "set-url", "origin", "https://example.com/magic-pro/qe-as-a-service")
        self.assertIsNone(activity.scope(another))

    def test_active_runs_do_not_overwrite_each_other_or_review_evidence(self):
        docs = self.root / "knowledge" / "findings"
        docs.mkdir(parents=True)
        (docs / "case-story-map.md").write_text(
            "---\ntype: Story Map\nstatus: pending-review\ntimestamp: 2026-01-15T11:00:00Z\n---\n"
        )
        agent = self.root / ".claude" / "agents" / "qe-analysis-agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nname: qe-analysis-agent\n---\n")
        for run in ("r1", "r2"):
            activity.record(self.journal, "tree", "qe-manual", run, "run-start",
                            agent="qe-analysis-agent", now=NOW - timedelta(minutes=5))
        activity.record(self.journal, "tree", "qe-manual", "r1", "run-exit",
                        agent="qe-analysis-agent", now=NOW)
        state = sources.snapshot(self.root, journal=self.journal, now=NOW)
        status = {lane["id"]: lane["status"] for lane in state["lanes"]}
        self.assertEqual(status["qe-analysis-agent"], "waiting")
        self.assertEqual(status["qe-manual:tree:r1:"], "done")
        self.assertEqual(status["qe-manual:tree:r2:"], "working")
        later = sources.snapshot(self.root, journal=self.journal, now=NOW + timedelta(minutes=30))
        self.assertEqual(next(lane["status"] for lane in later["lanes"]
                              if lane["id"].endswith(":r2:")), "unknown")

    def test_start_and_exit_from_an_actual_child_process(self):
        with patch.object(activity, "scope", return_value=(self.journal, "worktree")):
            exit_code = qe_run.launch("incident-agent", "qe-manual",
                                      [sys.executable, "-c", "raise SystemExit(4)"], cwd=self.root)
        self.assertEqual(exit_code, 4)
        state = sources.snapshot(self.root, journal=self.journal)
        self.assertEqual([e["status"] for e in state["timeline"]], ["working", "failed"])
        self.assertEqual(len({e["lane"] for e in state["timeline"]}), 1)

    def test_build_report_is_attributed_to_its_specialist(self):
        definitions = self.root / ".claude" / "agents"
        definitions.mkdir(parents=True)
        findings = self.root / "knowledge" / "findings"
        findings.mkdir(parents=True)
        for agent in ("builder-agent", "security-builder-executor", "performance-builder-executor"):
            (definitions / (agent + ".md")).write_text(f"---\nname: {agent}\n---\n")
        for agent in ("security-builder-executor", "performance-builder-executor"):
            (findings / (agent + "-build-report.md")).write_text(
                f"---\ntype: Build Report\ngenerated_by: {agent}\ntimestamp: 2026-01-15T11:00:00Z\n---\n"
            )
        state = sources.snapshot(self.root, journal=self.journal, now=NOW)
        self.assertCountEqual([ev["lane"] for ev in state["timeline"]],
                              ["security-builder-executor", "performance-builder-executor"])

    def test_launcher_defaults_to_copilot_and_forwards_model(self):
        with patch.object(qe_run, "launch", return_value=0) as launch:
            self.assertEqual(main(["run", "--model", "auto", "--read-only",
                                   "incident-agent", "Assess synthetic inputs"]), 0)
        launch.assert_called_once_with(
            "incident-agent", "qe-copilot",
            ["copilot", "--agent", "incident-agent", "-p", "Assess synthetic inputs",
             "--model", "auto", "--disable-builtin-mcps", "--available-tools", "view", "grep", "glob"],
            cwd=sources.REPO_ROOT,
        )

    def test_legacy_launcher_is_explicit_and_rejects_copilot_model(self):
        with patch.object(qe_run, "launch", return_value=4) as launch:
            self.assertEqual(main(["run", "--runtime", "claude",
                                   "incident-agent", "Assess synthetic inputs"]), 4)
            self.assertEqual(launch.call_args.args[2][0], "claude")
            with redirect_stderr(StringIO()) as stderr, self.assertRaises(SystemExit):
                main(["run", "--runtime", "claude", "--model", "auto",
                      "incident-agent", "Assess synthetic inputs"])
            self.assertIn("only supported with the Copilot runtime", stderr.getvalue())
            self.assertEqual(launch.call_count, 1)

    def test_writes_are_concurrent_and_history_is_bounded(self):
        activity.enable_copilot(self.journal, True)
        with patch.object(activity, "MAX_EVENTS", 4), ThreadPoolExecutor(4) as threads:
            list(threads.map(lambda n: activity.record(
                self.journal, "tree", "copilot", f"run-{n}", "session-start", now=NOW), range(12)))
        self.assertEqual(len(activity.read(self.journal, NOW)[1]), 4)
        self.assertEqual(activity.read(self.journal, NOW + timedelta(days=8))[1], [])

    def test_replay_starts_with_pre_window_evidence(self):
        activity.enable_copilot(self.journal, True)
        for hours, kind in [(25, "session-start"), (1, "session-end")]:
            activity.record(self.journal, "tree", "copilot", "s1", kind,
                            now=NOW - timedelta(hours=hours))
        state = sources.snapshot(self.root, journal=self.journal, now=NOW)
        self.assertEqual(state["initial"]["copilot:tree:s1:"]["status"], "idle")
        self.assertEqual([e["status"] for e in state["timeline"]], ["ended"])

    def test_server_serves_local_ui_and_journal_after_restart(self):
        activity.record(self.journal, "tree", "qe-manual", "r1", "run-start",
                        agent="incident-agent")
        with patch.object(activity, "scope", return_value=(self.journal, "tree")):
            httpd = server.serve(port=0, root=self.root)
        worker = Thread(target=httpd.serve_forever)
        worker.start()
        try:
            conn = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("GET", "/")
            page = conn.getresponse()
            self.assertEqual(page.status, 200)
            self.assertIn(b"QEaaS Agent Twin", page.read())
            conn.request("GET", "/api/state")
            self.assertIn(b"qe-manual:tree:r1:", conn.getresponse().read())
            conn.request("GET", "/api/state", headers={"Host": "not-local.example"})
            self.assertEqual(conn.getresponse().status, 400)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
