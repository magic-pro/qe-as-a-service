"""Local-only MCP server for repository agents."""

import os
from uuid import UUID

if os.environ.get("QE_AGENT_SERVICE_CHILD") == "1":
    raise SystemExit("QE agent child runtimes cannot start the local agent server.")

from mcp.server.fastmcp import FastMCP

from agent_service.app import AGENTS, LOCAL_ONLY, execute_agent
from agent_service.contracts import AgentRequest, AgentResult


def create_server():
    server = FastMCP("QEaaS local agents")

    def make_tool(name):
        async def invoke(task: str, run_id: UUID | None = None,
                         parent_run_id: UUID | None = None) -> AgentResult:
            """Run a local QE agent with the supplied task."""
            fields = {"task": task, "parent_run_id": parent_run_id}
            if run_id is not None:
                fields["run_id"] = run_id
            return await execute_agent(name, AgentRequest(**fields), local_stdio=True)
        return invoke

    for agent in AGENTS.values():
        description = agent.description
        if agent.name in LOCAL_ONLY:
            description += (" Local Copilot only; requires an approved Story map and matching "
                            "complete local-fixture decision. Writes and shell execution are denied.")
        elif agent.name == "builder-agent":
            description += " Requires a 'Story map: <workspace-relative-path>' line pointing to an approved map."
        server.add_tool(make_tool(agent.name), name=agent.name.replace("-", "_"),
                        title=agent.title, description=description)
    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
