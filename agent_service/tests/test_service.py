import asyncio
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from pydantic import ValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent_service import app as service
from agent_service.a2a_auth import CallerContextBuilder
from agent_service.contracts import AgentRequest, AgentResult
from agent_service.result_log import write_result

CLIENT_A = "A" * 43
CLIENT_B = "B" * 43


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_or_duplicate_a2a_keys_fail_closed(self):
        for value in ("not json", json.dumps({"alice": CLIENT_A, "bob": CLIENT_A}),
                      json.dumps({"alice": "short"})):
            with patch.dict(os.environ, {"QE_A2A_CLIENT_KEYS": value}):
                with self.assertRaises(ValueError):
                    CallerContextBuilder()

    async def test_result_records_parent_and_redacts_sensitive_patterns(self):
        run_id, parent_id = uuid4(), uuid4()
        request = AgentRequest(task="Synthetic task", run_id=run_id, parent_run_id=parent_id)
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"QE_AGENT_LOG_DIR": directory}), \
             patch.object(service, "MOCK", False), \
             patch.object(service, "run_agent", AsyncMock(return_value="demo@example.com ghp_syntheticsecret")):
            result = await service.execute_agent("planning-agent", request)
            path = Path(directory) / "agent-results.jsonl"
            record = json.loads(path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result.output, "demo@example.com ghp_syntheticsecret")
        self.assertEqual(record["run_id"], str(run_id))
        self.assertEqual(record["parent_run_id"], str(parent_id))
        self.assertEqual(record["agent"], "planning-agent")
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["mode"], "live")
        self.assertEqual(record["output"], "<email> <credential>")
        self.assertNotIn("task", record)
        AgentResult.model_validate(record)

    async def test_denial_is_logged_and_log_failure_is_reported(self):
        request = AgentRequest(task="Synthetic task")
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"QE_AGENT_LOG_DIR": directory}), \
             patch.object(service, "run_agent", AsyncMock(side_effect=service.AgentError("approval required"))):
            with self.assertRaisesRegex(service.AgentError, "approval required"):
                await service.execute_agent("builder-agent", request)
            record = json.loads((Path(directory) / "agent-results.jsonl").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error"], "approval required")
            self.assertIsNone(record["output"])
        with patch.object(service, "run_agent", AsyncMock(return_value="result")), \
             patch.object(service, "write_result", side_effect=PermissionError):
            with self.assertRaisesRegex(service.AgentError, "could not be logged"):
                await service.execute_agent("planning-agent", request)

    async def test_invalid_contract_and_non_private_log_are_rejected(self):
        with self.assertRaises(ValidationError):
            AgentRequest(task="  ")
        with self.assertRaises(ValidationError):
            AgentResult(run_id=uuid4(), agent="planning-agent", status="completed",
                        mode="live", error="failed")
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            with patch.dict(os.environ, {"QE_AGENT_LOG_DIR": directory}):
                result = AgentResult(run_id=uuid4(), agent="planning-agent", status="completed",
                                     mode="mock", output="synthetic")
                with self.assertRaises(PermissionError):
                    write_result(result)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_runtime_uses_selected_definition_without_skipping_permissions(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"result", b"")
        with patch.object(service, "MOCK", False), patch.object(service, "RUNTIME", "claude"), patch.object(
            asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
        ) as spawn:
            result = await service.run_agent("planning-agent", "Analyse this requirement")
        self.assertEqual(result, "result")
        self.assertEqual(spawn.call_args.args[:4], ("claude", "--agent", "planning-agent", "-p"))
        self.assertNotIn("--dangerously-skip-permissions", spawn.call_args.args)
        process.communicate.assert_awaited_once_with(b"Analyse this requirement")

    async def test_copilot_loads_existing_definition_in_isolated_profile(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"result", b"")
        observed = {}

        async def spawn(*args, **kwargs):
            observed["args"] = args
            observed["env"] = kwargs["env"]
            profile = Path(kwargs["env"]["COPILOT_HOME"]) / "agents" / "planning-agent.agent.md"
            observed["profile"] = profile.read_text(encoding="utf-8")
            return process

        with patch.object(service, "MOCK", False), patch.object(service, "RUNTIME", "copilot"), \
             patch.dict(os.environ, {"COPILOT_ALLOW_ALL": "true", "COPILOT_TRAMPOLINE_TOKEN": "private",
                                     "COPILOT_GITHUB_TOKEN": "test-token",
                                     "QE_A2A_CLIENT_KEYS": "private-keys"}), \
             patch.object(asyncio, "create_subprocess_exec", AsyncMock(side_effect=spawn)):
            self.assertEqual(await service.run_agent("planning-agent", "Synthetic task"), "result")
        self.assertEqual(observed["args"][:5], ("copilot", "--agent", "planning-agent", "-p", "Synthetic task"))
        original = (service.ROOT / ".claude/agents/planning-agent.md").read_text(encoding="utf-8")
        self.assertTrue(observed["profile"].endswith(original.split("---", 2)[2]))
        self.assertEqual(observed["env"]["COPILOT_ALLOW_ALL"], "false")
        self.assertEqual(observed["env"]["COPILOT_ASSISTED_APPROVAL"], "false")
        self.assertEqual(observed["env"]["COPILOT_GITHUB_TOKEN"], "test-token")
        self.assertNotIn("COPILOT_TRAMPOLINE_TOKEN", observed["env"])
        self.assertNotIn("QE_A2A_CLIENT_KEYS", observed["env"])
        self.assertFalse(Path(observed["env"]["COPILOT_HOME"]).exists())
        process.communicate.assert_awaited_once_with(None)

    async def test_local_specialists_require_approved_track_and_local_fixture(self):
        with tempfile.TemporaryDirectory(dir=service.ROOT) as folder:
            root = Path(folder)
            target = root / "target"
            target.mkdir()
            subprocess.run(["git", "init", "-q", str(target)], check=True)
            fixture = target / "fixture.json"
            fixture.write_text("{}", encoding="utf-8")
            story = root / "story.md"
            prompt = f"Story map: {story.relative_to(service.ROOT)}"
            common = (f"planning: docs/security-performance-handoff.md; target: {target.relative_to(service.ROOT)}; "
                      f"fixture: {fixture.relative_to(service.ROOT)}; fixture-kind: synthetic; "
                      "expected: synthetic allow and deny")
            def write_map(status, notes, decision="Build new test"):
                story.write_text(
                    f"---\ntype: Story Map\nstatus: {status}\n---\n## Human Review Required\n"
                    f"| Signal key | Decision | Notes |\n| --- | --- | --- |\n"
                    f"| SYNTHETIC | {decision} | {notes} |\n", encoding="utf-8")
            write_map("pending-review", f"track: security; {common}")
            with self.assertRaisesRegex(service.AgentError, "status: approved"):
                await service.run_agent("security-builder-executor", prompt, local_stdio=True)
            write_map("approved", f"track: security; {common}", "Skip")
            with self.assertRaisesRegex(service.AgentError, "no approved security row"):
                await service.run_agent("security-builder-executor", prompt, local_stdio=True)
            write_map("approved", f"track: security; {common}")
            with patch.object(service, "MOCK", True), patch.object(service, "RUNTIME", "copilot"):
                self.assertIn("MOCK ONLY", await service.run_agent("security-builder-executor", prompt, local_stdio=True))
                with self.assertRaisesRegex(service.AgentError, "no approved performance row"):
                    await service.run_agent("performance-builder-executor", prompt, local_stdio=True)
                write_map("approved", f"track: performance; {common}; workload: 10 records; warm-up: 0; "
                          "sample-size: 3; concurrency: 1; time-limit: 5s; measurement: p95; "
                          "budget: 100ms; environment: local")
                self.assertIn("MOCK ONLY", await service.run_agent("performance-builder-executor", prompt, local_stdio=True))
                write_map("approved", f"track: performance; {common}; workload: 10 records; warm-up: 0; "
                          "sample-size: 3; concurrency: 0; time-limit: 5s; measurement: p95; "
                          "budget: 100ms; environment: local")
                with self.assertRaisesRegex(service.AgentError, "no approved performance row"):
                    await service.run_agent("performance-builder-executor", prompt, local_stdio=True)
                write_map("approved", f"track: performance; {common}; workload: 10 records; warm-up: 0; "
                          "sample-size: 3; concurrency: 1; time-limit: 5s; measurement: p95; "
                          "budget: 100ms; environment: local")
                fixture.unlink()
                with self.assertRaisesRegex(service.AgentError, "complete local fixture"):
                    await service.run_agent("performance-builder-executor", prompt, local_stdio=True)

    async def test_local_specialist_preserves_restricted_profile(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"result", b"")
        observed = {}

        async def spawn(*args, **kwargs):
            observed["args"] = args
            observed["env"] = kwargs["env"]
            path = Path(kwargs["env"]["COPILOT_HOME"]) / "agents" / "security-builder-executor.agent.md"
            observed["profile"] = path.read_text(encoding="utf-8")
            return process

        with patch.object(service, "MOCK", False), patch.object(service, "RUNTIME", "copilot"), \
             patch.object(service, "approved_specialist_map", return_value=("story.md", "approved")), \
             patch.object(asyncio, "create_subprocess_exec", AsyncMock(side_effect=spawn)):
            self.assertEqual(await service.run_agent("security-builder-executor", "task", local_stdio=True), "result")
        self.assertIn("strict-tools-list: true", observed["profile"])
        self.assertIn("- execute", observed["profile"])
        self.assertIn("--disable-builtin-mcps", observed["args"])
        self.assertIn("--deny-tool", observed["args"])
        self.assertIn("shell", observed["args"])
        self.assertIn("write", observed["args"])
        self.assertIn("qe-agents-local", observed["args"])
        self.assertEqual(observed["env"]["QE_AGENT_SERVICE_CHILD"], "1")

    async def test_builder_requires_approved_map_and_specialists_remain_local(self):
        with tempfile.TemporaryDirectory(dir=service.ROOT) as folder:
            path = Path(folder) / "story.md"
            path.write_text("---\ntype: Story Map\nstatus: pending-review\n---\n", encoding="utf-8")
            prompt = f"Story map: {path.relative_to(service.ROOT)}"
            with self.assertRaisesRegex(service.AgentError, "status: approved"):
                await service.run_agent("builder-agent", prompt)
            path.write_text("---\ntype: Story Map\nstatus: approved\n---\n", encoding="utf-8")
            with patch.object(service, "MOCK", True):
                self.assertIn("MOCK ONLY", await service.run_agent("builder-agent", prompt))
            for name in service.LOCAL_ONLY:
                with self.assertRaisesRegex(service.AgentError, "local Copilot session"):
                    await service.run_agent(name, prompt)
            with self.assertRaisesRegex(service.AgentError, "inside the service workspace"):
                await service.run_agent("builder-agent", "Story map: /etc/passwd")

    async def test_only_approved_story_map_is_accepted_and_invalid_utf8_is_logged(self):
        with tempfile.TemporaryDirectory(dir=service.ROOT) as folder, tempfile.TemporaryDirectory() as logs:
            path = Path(folder) / "story.md"
            prompt = f"Story map: {path.relative_to(service.ROOT)}"
            path.write_text("---\ntype: Design Spec\nstatus: approved\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(service.AgentError, "type: Story Map"):
                await service.run_agent("builder-agent", prompt)
            path.write_bytes(b"\xff")
            with patch.dict(os.environ, {"QE_AGENT_LOG_DIR": logs}):
                with self.assertRaisesRegex(service.AgentError, "UTF-8"):
                    await service.execute_agent("builder-agent", AgentRequest(task=prompt))
                record = json.loads((Path(logs) / "agent-results.jsonl").read_text())
                self.assertEqual(record["status"], "failed")
                self.assertIn("UTF-8", record["error"])

    async def test_approval_is_rechecked_after_waiting_and_snapshot_is_used(self):
        with tempfile.TemporaryDirectory(dir=service.ROOT) as folder:
            path = Path(folder) / "story.md"
            prompt = f"Story map: {path.relative_to(service.ROOT)}"
            approved = "---\ntype: Story Map\nstatus: approved\n---\nApproved content\n"
            path.write_text(approved, encoding="utf-8")
            process = AsyncMock()
            process.returncode = 0
            process.communicate.return_value = (b"result", b"")
            observed = {}

            async def spawn(*args, **kwargs):
                command_prompt = args[4]
                snapshot_path = service.ROOT / command_prompt.split("Story map: ", 1)[1].splitlines()[0]
                observed["snapshot"] = snapshot_path.read_text()
                observed["mode"] = snapshot_path.stat().st_mode & 0o777
                observed["path"] = snapshot_path
                path.write_text("---\ntype: Story Map\nstatus: pending-review\n---\n")
                return process

            with patch.object(service, "MOCK", False), patch.object(service, "RUNTIME", "copilot"), \
                 patch.object(asyncio, "create_subprocess_exec", AsyncMock(side_effect=spawn)):
                await service.RUN_LOCK.acquire()
                try:
                    pending = asyncio.create_task(service.run_agent("builder-agent", prompt))
                    await asyncio.sleep(0)
                    path.write_text("---\ntype: Story Map\nstatus: pending-review\n---\n")
                finally:
                    service.RUN_LOCK.release()
                with self.assertRaisesRegex(service.AgentError, "status: approved"):
                    await pending
                path.write_text(approved)
                self.assertEqual(await service.run_agent("builder-agent", prompt), "result")
            self.assertEqual(observed["snapshot"], approved)
            self.assertEqual(observed["mode"], 0o400)
            self.assertFalse(observed["path"].exists())

    async def test_termination_kills_descendant_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "child-ran"
            child_code = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).touch()"
            parent_code = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
                "print('ready',flush=True); time.sleep(30)"
            )
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", parent_code, start_new_session=True,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            self.assertEqual(await asyncio.wait_for(process.stdout.readline(), 5), b"ready\n")
            await service.terminate_process_group(process)
            await asyncio.sleep(1.2)
            self.assertFalse(marker.exists())

    async def test_timeout_and_cancellation_release_the_run_lock(self):
        for failure in (asyncio.TimeoutError(), asyncio.CancelledError()):
            process = AsyncMock()
            process.communicate.side_effect = failure
            with patch.object(service, "MOCK", False), patch.object(service, "RUNTIME", "claude"), \
                 patch.object(asyncio, "create_subprocess_exec", AsyncMock(return_value=process)) as spawn, \
                 patch.object(service, "terminate_process_group", AsyncMock()) as terminate:
                error = service.AgentError if isinstance(failure, asyncio.TimeoutError) else asyncio.CancelledError
                with self.assertRaises(error):
                    await service.run_agent("planning-agent", "Synthetic task")
                self.assertTrue(spawn.call_args.kwargs["start_new_session"])
                terminate.assert_awaited_once_with(process)
                self.assertFalse(service.RUN_LOCK.locked())


class BuildStagingTests(unittest.TestCase):
    def test_only_intended_inputs_are_staged(self):
        script = service.ROOT / "deploy/cloud-run/stage-agents.py"
        spec = importlib.util.spec_from_file_location("qe_stage_agents", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            root, dest = Path(source), Path(destination)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in (*module.SERVICE_INPUTS, "docs/tracked.md", ".mcp.json",
                         "docs/private.log", "docs/.mcp.json", "ci-output/test.json"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "docs/tracked.md", ".mcp.json"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "-f", "docs/private.log", "docs/.mcp.json"],
                           check=True)
            (root / "docs/tracked.md").chmod(0o755)
            module.stage_inputs(root, dest)
            staged = {str(path.relative_to(dest)) for path in dest.rglob("*") if path.is_file()}
            self.assertEqual(staged, set(module.SERVICE_INPUTS) | {"docs/tracked.md"})
            self.assertNotIn(".mcp.json", staged)
            self.assertNotIn("docs/private.log", staged)
            self.assertNotIn("docs/.mcp.json", staged)
            self.assertNotIn("ci-output/test.json", staged)
            self.assertEqual((dest / "docs/tracked.md").stat().st_mode & 0o777, 0o755)


class LiveProtocolTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(dir=service.ROOT)
        path = Path(cls.fixture.name) / "story.md"
        path.write_text("---\ntype: Story Map\nstatus: approved\n---\nSynthetic fixture.\n", encoding="utf-8")
        cls.story_map = str(path.relative_to(service.ROOT))
        cls.log_dir = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "QE_AGENT_MOCK": "true", "QE_AGENT_BASE_URL": cls.url,
               "QE_AGENT_LOG_DIR": cls.log_dir.name,
               "QE_A2A_CLIENT_KEYS": json.dumps({"alice": CLIENT_A, "bob": CLIENT_B})}
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "agent_service.app:app",
             "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=service.ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                if httpx.get(f"{cls.url}/health", timeout=0.2).status_code == 200:
                    return
            except httpx.RequestError:
                pass
            if cls.server.poll() is not None:
                break
            time.sleep(0.1)
        cls.server.terminate()
        cls.server.wait()
        cls.fixture.cleanup()
        cls.log_dir.cleanup()
        raise RuntimeError("Service failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=10)
        cls.fixture.cleanup()
        cls.log_dir.cleanup()

    async def test_mcp_lists_and_calls_every_agent(self):
        async with streamable_http_client(f"{self.url}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                self.assertEqual({tool.name for tool in tools.tools},
                                 {name.replace("-", "_") for name in service.AGENTS})
                for name in service.AGENTS:
                    task = f"Story map: {self.story_map}" if name == "builder-agent" else "Synthetic sample"
                    result = await session.call_tool(name.replace("-", "_"), {"task": task})
                    if name in service.LOCAL_ONLY:
                        self.assertTrue(result.isError, name)
                        self.assertIn("local Copilot session", result.content[0].text)
                    else:
                        self.assertFalse(result.isError, name)
                        self.assertIn("MOCK ONLY", result.content[0].text)

                run_id, parent_id = str(uuid4()), str(uuid4())
                result = await session.call_tool("planning_agent", {
                    "task": "Synthetic task", "run_id": run_id, "parent_run_id": parent_id,
                })
                self.assertEqual(result.structuredContent["run_id"], run_id)
                self.assertEqual(result.structuredContent["parent_run_id"], parent_id)
                self.assertEqual(result.structuredContent["agent"], "planning-agent")
                self.assertEqual(result.structuredContent["mode"], "mock")

    async def test_a2a_cards_and_tasks_for_every_agent(self):
        async with httpx.AsyncClient() as client:
            for name in service.AGENTS:
                base = f"{self.url}/a2a/{name}"
                card_response = await client.get(f"{base}/.well-known/agent-card.json")
                card_response.raise_for_status()
                card = card_response.json()
                self.assertEqual(card["supportedInterfaces"][0]["url"], base)
                self.assertEqual(card["skills"][0]["id"], name)
                prompt = f"Story map: {self.story_map}" if name == "builder-agent" else "Synthetic sample"
                response = await client.post(base, headers={"A2A-Version": "1.0", "X-QE-A2A-Key": CLIENT_A}, json={
                    "jsonrpc": "2.0", "id": str(uuid4()), "method": "SendMessage",
                    "params": {"message": {"messageId": str(uuid4()), "role": "ROLE_USER",
                                           "parts": [{"text": prompt}]}},
                })
                response.raise_for_status()
                task = response.json()["result"]["task"]
                if name in service.LOCAL_ONLY:
                    self.assertEqual(task["status"]["state"], "TASK_STATE_FAILED", name)
                    self.assertIn("local Copilot session", task["status"]["message"]["parts"][0]["text"])
                else:
                    self.assertEqual(task["status"]["state"], "TASK_STATE_COMPLETED", name)
                    self.assertIn("MOCK ONLY", task["artifacts"][0]["parts"][0]["text"])

    async def test_a2a_returns_the_same_contract_and_parent(self):
        run_id, parent_id = str(uuid4()), str(uuid4())
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.url}/a2a/planning-agent",
                                         headers={"A2A-Version": "1.0", "X-QE-A2A-Key": CLIENT_A}, json={
                "jsonrpc": "2.0", "id": str(uuid4()), "method": "SendMessage",
                "params": {"message": {"messageId": str(uuid4()), "role": "ROLE_USER",
                                       "parts": [{"text": "Synthetic task"}],
                                       "metadata": {"run_id": run_id, "parent_run_id": parent_id}}},
            })
        response.raise_for_status()
        result = json.loads(response.json()["result"]["task"]["artifacts"][0]["parts"][0]["text"])
        self.assertEqual(result["run_id"], run_id)
        self.assertEqual(result["parent_run_id"], parent_id)
        self.assertEqual(result["agent"], "planning-agent")
        self.assertEqual(result["status"], "completed")
        AgentResult.model_validate(result)

    async def test_a2a_requires_credentials_and_isolates_task_history(self):
        base = f"{self.url}/a2a/planning-agent"
        def body(method, params):
            return {"jsonrpc": "2.0", "id": str(uuid4()), "method": method, "params": params}
        async with httpx.AsyncClient() as client:
            message = body("SendMessage", {"message": {
                "messageId": str(uuid4()), "role": "ROLE_USER", "parts": [{"text": "synthetic"}],
            }})
            unauthenticated = await client.post(base, headers={"A2A-Version": "1.0",
                                                               "X-QE-A2A-User": "alice"}, json=message)
            self.assertEqual(unauthenticated.status_code, 401)
            alice = {"A2A-Version": "1.0", "X-QE-A2A-Key": CLIENT_A}
            bob = {"A2A-Version": "1.0", "X-QE-A2A-Key": CLIENT_B}
            created = await client.post(base, headers=alice, json=message)
            task_id = created.json()["result"]["task"]["id"]
            own = await client.post(base, headers=alice, json=body("GetTask", {"id": task_id}))
            self.assertEqual(own.json()["result"]["id"], task_id)
            for method in ("GetTask", "CancelTask"):
                denied = await client.post(base, headers=bob, json=body(method, {"id": task_id}))
                self.assertIn("error", denied.json())
            continuation = body("SendMessage", {"message": {
                "messageId": str(uuid4()), "taskId": task_id, "role": "ROLE_USER",
                "parts": [{"text": "synthetic follow-up"}],
            }})
            denied = await client.post(base, headers=bob, json=continuation)
            self.assertIn("error", denied.json())
            listed = await client.post(base, headers=bob, json=body("ListTasks", {}))
            self.assertNotIn(task_id, [task["id"] for task in listed.json()["result"].get("tasks", [])])


class StdioProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_runtime_cannot_start_another_local_server(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "agent_service.stdio", cwd=service.ROOT,
            env={**os.environ, "QE_AGENT_SERVICE_CHILD": "1"},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(stdout)
        self.assertIn(b"cannot start the local agent server", stderr)

    async def test_example_config_launches_and_lists_all_agents(self):
        config = json.loads((service.ROOT / "agent_service/mcp-stdio.example.json").read_text())
        definition = config["mcpServers"]["qe-agents-local"]
        with tempfile.TemporaryDirectory() as directory:
            params = StdioServerParameters(command=definition["command"], args=definition["args"],
                                           cwd=service.ROOT, env={**os.environ, "QE_AGENT_MOCK": "true",
                                                                 "QE_AGENT_LOG_DIR": directory})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools},
                                     {name.replace("-", "_") for name in service.AGENTS})
                    result = await session.call_tool("security_builder_executor", {"task": "Synthetic task"})
                    self.assertTrue(result.isError)
                    self.assertIn("Story map", result.content[0].text)
                    parent_id = str(uuid4())
                    result = await session.call_tool("planning_agent", {
                        "task": "Synthetic task", "parent_run_id": parent_id,
                    })
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent["parent_run_id"], parent_id)
                    self.assertEqual(result.structuredContent["mode"], "mock")
