"""MCP and A2A adapters for the existing QE agent definitions."""

import asyncio
import json
import os
import re
import signal
import subprocess
import tempfile
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part, Task,
    TaskState, TaskStatus,
)
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_service.a2a_auth import CallerContextBuilder
from agent_service.contracts import AgentRequest, AgentResult
from agent_service.result_log import write_result

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("QE_AGENT_BASE_URL", "http://127.0.0.1:8083").rstrip("/")
MOCK = os.environ.get("QE_AGENT_MOCK", "false").lower() == "true"
TIMEOUT = int(os.environ.get("QE_AGENT_TIMEOUT_SECONDS", "240"))
RUNTIME = os.environ.get("QE_AGENT_RUNTIME", "copilot").lower()
if RUNTIME not in {"copilot", "claude"}:
    raise ValueError("QE_AGENT_RUNTIME must be copilot or claude")
LOCAL_ONLY = {"security-builder-executor", "performance-builder-executor"}
GATED = {"builder-agent"}
RUN_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class Agent:
    name: str
    title: str
    description: str


def load_agents():
    agents = {}
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f"Invalid agent frontmatter: {path}")
        data = yaml.safe_load(parts[1])
        if not isinstance(data, dict) or data.get("name") != path.stem:
            raise ValueError(f"Invalid agent name: {path}")
        name, title, description = (data.get(key) for key in ("name", "title", "description"))
        if not all(isinstance(item, str) and item.strip() for item in (name, title, description)):
            raise ValueError(f"Missing agent metadata: {path}")
        agents[name] = Agent(name, title, description)
    if not agents:
        raise ValueError("No agent definitions found")
    return agents


AGENTS = load_agents()


class AgentError(Exception):
    pass


def approved_story_map(prompt: str) -> tuple[str, str]:
    match = re.search(r"(?m)^Story map:\s*(\S+)\s*$", prompt, re.IGNORECASE)
    if not match:
        raise AgentError("An approved local Story map: <relative-path> line is required.")
    path = (ROOT / match.group(1)).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise AgentError("Story map must be an existing file inside the service workspace.")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AgentError("Story map could not be read as UTF-8.") from exc
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise AgentError("Story map is missing YAML frontmatter.")
    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise AgentError("Story map frontmatter is invalid.") from exc
    if not isinstance(metadata, dict) or metadata.get("status") != "approved":
        raise AgentError("Story map must have status: approved before building.")
    if metadata.get("type") != "Story Map":
        raise AgentError("Approved document must have type: Story Map.")
    return str(path.relative_to(ROOT)), text


def approved_specialist_map(name: str, prompt: str) -> tuple[str, str]:
    path, text = approved_story_map(prompt)
    match = re.search(r"(?im)^##[ \t]+[^\n]*Human Review Required[^\n]*\n(.*?)(?=^#{1,2}[ \t]+|\Z)",
                      text, re.DOTALL)
    if not match:
        raise AgentError("Story map requires a Human Review Required decision table.")
    track = "security" if name == "security-builder-executor" else "performance"
    for line in match.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3 or cells[1].lower() not in {"build new test", "update assertion"}:
            continue
        fields = {}
        for item in cells[2].split(";"):
            key, separator, value = item.partition(":")
            if separator:
                fields[key.strip().lower()] = value.strip().strip("`")
        if fields.get("track", "").lower() != track:
            continue
        required = {"planning", "target", "fixture", "fixture-kind", "expected"}
        if track == "performance":
            required |= {"workload", "warm-up", "sample-size", "concurrency",
                         "time-limit", "measurement", "budget", "environment"}
        if any(not fields.get(key) for key in required):
            continue
        planning = (ROOT / fields["planning"]).resolve()
        target = (ROOT / fields["target"]).resolve()
        fixture = (ROOT / fields["fixture"]).resolve()
        if (not planning.is_relative_to(ROOT) or not planning.is_file()
                or not target.is_relative_to(ROOT) or not target.is_dir()
                or not fixture.is_relative_to(target) or not fixture.exists()
                or fields["fixture-kind"].lower() not in {"synthetic", "local-mock"}):
            continue
        if not (target / ".git").exists():
            continue
        try:
            checkout = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
                check=True, capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if Path(checkout.stdout.strip()).resolve() != target:
            continue
        if track == "performance":
            if not all(re.fullmatch(r"[1-9]\d*", fields[key])
                       for key in ("sample-size", "concurrency")):
                continue
            if not re.fullmatch(r"\d+", fields["warm-up"]):
                continue
            if not re.fullmatch(r"[1-9]\d*(?:s|m)", fields["time-limit"]):
                continue
        return path, text
    raise AgentError(f"Story map has no approved {track} row with complete local fixture and criteria.")


def project_mcp_servers() -> set[str]:
    names = {"qe-agents-local"}
    for path in (ROOT / ".mcp.json", ROOT / ".github" / "mcp.json"):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise AgentError(f"Invalid MCP configuration: {path.name}")
            servers = data.get("mcpServers", data)
            if not isinstance(servers, dict):
                raise AgentError(f"Invalid MCP configuration: {path.name}")
            names.update(servers)
    return names


async def run_agent(name: str, prompt: str, *, local_stdio: bool = False) -> str:
    if name not in AGENTS:
        raise AgentError("Unknown QE agent.")
    if not prompt.strip() or len(prompt) > 32000:
        raise AgentError("Provide a non-empty task of at most 32000 characters.")
    if name in LOCAL_ONLY and not local_stdio:
        raise AgentError("This agent is restricted to a local Copilot session; network execution is disabled.")
    async with RUN_LOCK:
        approved = None
        if name in LOCAL_ONLY:
            if RUNTIME != "copilot":
                raise AgentError("Local specialists require the Copilot runtime.")
            approved = approved_specialist_map(name, prompt)
        elif name in GATED:
            approved = approved_story_map(prompt)
        if MOCK:
            return f"MOCK ONLY: {name} received the task; no agent was executed."
        with tempfile.TemporaryDirectory(prefix="qe-copilot-") as home, ExitStack() as stack:
            if approved is not None:
                original, text = approved
                snapshot_dir = stack.enter_context(
                    tempfile.TemporaryDirectory(prefix=".qe-approved-", dir=ROOT)
                )
                snapshot = Path(snapshot_dir) / "story-map.md"
                snapshot.write_text(text, encoding="utf-8")
                snapshot.chmod(0o400)
                relative_snapshot = snapshot.relative_to(ROOT)
                prompt = re.sub(r"(?m)^Story map:\s*(\S+)\s*$",
                                lambda _: f"Story map: {relative_snapshot}", prompt,
                                count=1, flags=re.IGNORECASE)
                prompt += (f"\n\nUse the approved snapshot above, not the original file, for all decisions. "
                           f"Original Story Map path for traceability: {original}")
            env = os.environ.copy()
            env.pop("QE_A2A_CLIENT_KEYS", None)
            env["QE_AGENT_SERVICE_CHILD"] = "1"
            if RUNTIME == "copilot":
                for key in list(env):
                    if (key.startswith("COPILOT_") and not key.startswith("COPILOT_PROVIDER_")
                            and key not in {"COPILOT_GITHUB_TOKEN", "COPILOT_MODEL", "COPILOT_OFFLINE"}):
                        del env[key]
                agent = AGENTS[name]
                if name in LOCAL_ONLY:
                    text = (ROOT / ".github" / "agents" / f"{name}.agent.md").read_text(encoding="utf-8")
                    parts = text.split("---", 2)
                    profile = yaml.safe_load(parts[1])
                    if not isinstance(profile, dict) or profile.get("name") != name:
                        raise AgentError("Invalid local specialist profile.")
                    profile["strict-tools-list"] = True
                    body = parts[2]
                else:
                    text = (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
                    body = text.split("---", 2)[2]
                    profile = {"name": name, "description": agent.description}
                agent_dir = Path(home) / "agents"
                agent_dir.mkdir()
                metadata = yaml.safe_dump(profile, allow_unicode=True)
                (agent_dir / f"{name}.agent.md").write_text(
                    f"---\n{metadata}---\n{body}", encoding="utf-8"
                )
                env.update({"COPILOT_HOME": home, "COPILOT_ALLOW_ALL": "false",
                            "COPILOT_ASSISTED_APPROVAL": "false", "AUTO_APPROVAL": "false",
                            "QE_AGENT_SERVICE_CHILD": "1"})
                command = ["copilot", "--agent", name, "-p", prompt, "--silent",
                           "--no-ask-user", "--no-auto-update", "--stream", "off"]
                if name in LOCAL_ONLY:
                    env["COPILOT_PLUGIN_DIR_ONLY"] = "true"
                    command.extend(["--disable-builtin-mcps", "--deny-tool", "shell", "--deny-tool", "write"])
                    for server in sorted(project_mcp_servers()):
                        command.extend(["--disable-mcp-server", server])
                else:
                    command.extend(["--disable-mcp-server", "qe-agents-local"])
                if name not in LOCAL_ONLY and (mcp_config := os.environ.get("QE_MCP_CONFIG")):
                    command.extend(["--additional-mcp-config", f"@{mcp_config}"])
                stdin, input_bytes = asyncio.subprocess.DEVNULL, None
            else:
                command = ["claude", "--agent", name, "-p", "--output-format", "text",
                           "--permission-mode", "dontAsk"]
                if mcp_config := os.environ.get("QE_MCP_CONFIG"):
                    command.extend(["--mcp-config", mcp_config, "--strict-mcp-config"])
                stdin, input_bytes = asyncio.subprocess.PIPE, prompt.encode()
            try:
                process = await asyncio.create_subprocess_exec(
                    *command, cwd=ROOT, env=env, stdin=stdin,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                raise AgentError(f"{RUNTIME} runtime could not be started.") from exc
            try:
                stdout, _stderr = await asyncio.wait_for(process.communicate(input_bytes), TIMEOUT)
            except asyncio.TimeoutError as exc:
                await terminate_process_group(process)
                raise AgentError("Agent execution timed out.") from exc
            except asyncio.CancelledError:
                await terminate_process_group(process)
                raise
            if process.returncode:
                raise AgentError(f"{RUNTIME} runtime failed with exit code {process.returncode}; check runtime credentials and configuration.")
            response = stdout.decode("utf-8", errors="replace").strip()
            if not response:
                raise AgentError(f"{RUNTIME} runtime returned an empty response.")
            return response


async def terminate_process_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise AgentError("Failed to terminate the agent process group.") from exc
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError as exc:
        raise AgentError("Agent process cleanup timed out.") from exc


async def execute_agent(name: str, request: AgentRequest, *, local_stdio: bool = False) -> AgentResult:
    try:
        output = await run_agent(name, request.task, local_stdio=local_stdio)
        result = AgentResult(run_id=request.run_id, parent_run_id=request.parent_run_id,
                             agent=name, status="completed", mode="mock" if MOCK else "live",
                             output=output)
    except AgentError as exc:
        result = AgentResult(run_id=request.run_id, parent_run_id=request.parent_run_id,
                             agent=name, status="failed", mode="mock" if MOCK else "live",
                             error=str(exc))
    try:
        write_result(result)
    except OSError as exc:
        raise AgentError("Agent result could not be logged; check the private log directory.") from exc
    if result.status == "failed":
        raise AgentError(result.error)
    return result


class QEExecutor(AgentExecutor):
    def __init__(self, agent: Agent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task_id, context_id = context.task_id, context.context_id
        if not context.message or not task_id or not context_id:
            raise ValueError("A message, task ID, and context ID are required")
        await event_queue.enqueue_event(Task(
            id=task_id, context_id=context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED), history=[context.message],
        ))
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        try:
            metadata = dict(context.message.metadata)
            request = AgentRequest(task=context.get_user_input(),
                                   **{key: metadata[key] for key in ("run_id", "parent_run_id")
                                      if key in metadata})
            result = await execute_agent(self.agent.name, request)
        except (AgentError, ValueError) as exc:
            await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
            return
        await updater.add_artifact([Part(text=result.model_dump_json())], name="response", last_chunk=True)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def create_app():
    a2a_context = CallerContextBuilder()
    mcp = FastMCP("QEaaS agents", host="0.0.0.0", stateless_http=True, json_response=True)

    def make_tool(name):
        async def invoke(task: str, run_id: UUID | None = None,
                         parent_run_id: UUID | None = None) -> AgentResult:
            """Run a QE agent with the supplied task."""
            fields = {"task": task, "parent_run_id": parent_run_id}
            if run_id is not None:
                fields["run_id"] = run_id
            return await execute_agent(name, AgentRequest(**fields))
        return invoke

    for agent in AGENTS.values():
        description = agent.description
        if agent.name in LOCAL_ONLY:
            description += " Network execution is disabled; use a local Copilot session."
        elif agent.name in GATED:
            description += " Requires a 'Story map: <workspace-relative-path>' line pointing to an approved map."
        mcp.add_tool(make_tool(agent.name), name=agent.name.replace("-", "_"),
                     title=agent.title, description=description)
    mcp_app = mcp.streamable_http_app()
    routes = list(mcp_app.routes)
    routes.append(Route("/health", lambda request: JSONResponse({"status": "ok"})))
    for agent in AGENTS.values():
        prefix = f"/a2a/{agent.name}"
        description = agent.description
        if agent.name in LOCAL_ONLY:
            description += " Network execution is disabled; use a local Copilot session."
        elif agent.name in GATED:
            description += " Requires a 'Story map: <workspace-relative-path>' line pointing to an approved map."
        card = AgentCard(
            name=agent.title, description=description, version="1.0.0",
            capabilities=AgentCapabilities(streaming=False),
            default_input_modes=["text"], default_output_modes=["text"],
            supported_interfaces=[AgentInterface(
                protocol_binding="JSONRPC", protocol_version="1.0",
                url=f"{BASE_URL}{prefix}",
            )],
            skills=[AgentSkill(id=agent.name, name=agent.title,
                               description=description, tags=["qe"])],
        )
        handler = DefaultRequestHandler(
            agent_executor=QEExecutor(agent), task_store=InMemoryTaskStore(), agent_card=card,
        )
        routes.extend(create_agent_card_routes(card, card_url=f"{prefix}/.well-known/agent-card.json"))
        routes.extend(create_jsonrpc_routes(handler, rpc_url=prefix, context_builder=a2a_context))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    return Starlette(routes=routes, lifespan=lifespan)


app = create_app()
