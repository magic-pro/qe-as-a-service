---
type: Architecture
title: QE agent network service
description: Deployment, protocol access, runtime authentication, and approval limits for the QE agent service.
timestamp: 2026-11-20T00:00:00Z
tags: [agents, mcp, a2a]
---

# QE agent network service

The service discovers `.claude/agents/*.md` at startup and publishes each
definition's name and description. MCP and A2A are **interfaces**, not agent
runtimes. By default, real calls start GitHub Copilot CLI in the service
workspace. The service copies the selected Markdown body into a temporary,
isolated Copilot agent profile and invokes `copilot --agent <name> -p`.
Repository instructions remain enabled, and the temporary profile and state
are removed after each request. Set `QE_AGENT_RUNTIME=claude` to instead invoke
Claude Code directly against the same definitions. Neither backend maintains a
second copy of the prompts in source control.

Local stdio exposes all seven agents. For the two specialists it uses the
existing `.github/agents/*.agent.md` profile, including its tool list, with
strict tool-list enforcement. Their [handoff](security-performance-handoff.md)
requires local Copilot and local fixtures: they remain unavailable over
HTTP/MCP and A2A. Test-creator and test-healer are target-repository templates,
not agents in this repository; run them in their target checkout instead.

## Credentials and permissions

The image includes Copilot CLI and Claude Code. For the default backend supply
`COPILOT_GITHUB_TOKEN`: a supported GitHub token for an eligible Copilot
account, such as a personal fine-grained token with **Copilot Requests**
permission. See [Copilot CLI authentication](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli).
Copilot plan and organization policies apply. The Claude backend instead
requires `ANTHROPIC_API_KEY` or another supported Claude Code provider;
Anthropic API billing is separate. A Copilot subscription is **not** an
Anthropic API key.

Copilot runs non-interactively without `--allow-all` or assisted approval;
the service explicitly disables the equivalent environment flags. Its
permissions are distinct from `.claude/settings.json`. The optional Claude
backend uses `dontAsk` and the existing Claude settings. Tools requiring
interactive approval can be denied, so a response may request human action
instead of performing writes or raising PRs. Do not grant blanket tool
permissions to compensate. GitHub, Jira and Confluence credentials are
separate from model credentials. The image does not include `.mcp.json`:
provide a correctly authenticated MCP configuration via a securely mounted
file and set `QE_MCP_CONFIG` to its path. Copilot loads it as an additional
configuration; Claude uses it as its strict MCP configuration. GCP and OTEL
MCP integrations are not configured in this repository.

Copilot CLI receives the task as a command-line argument, which may be visible
to other processes with access to the process list. Do not include secrets or
unmasked customer data in a task.

**Trust boundary:** HTTP MCP has no built-in authentication. It executes
requests with the service identity and configured tools, so never expose it
publicly. Compose binds to loopback; a remote deployment must enforce
authentication and authorization at the ingress. A2A additionally requires
individual client keys as described below. Cloud Run should require IAM
authentication and grant `roles/run.invoker` only to trusted callers. Do not
grant `allUsers` or disable the IAM invoker check. Cloud Run ID tokens are
separate from the model and upstream credentials. Requests and responses can
contain sensitive data: use synthetic or masked data, TLS remotely, and
appropriate access controls.

## Approval gates and storage

The builder rejects requests without a line `Story map: <relative-path>` to a
workspace file with YAML frontmatter `type: Story Map` and `status: approved`.
Approval is checked after the request acquires the run lock; the runtime receives
a private read-only snapshot of that approved content. This guards against
ordinary edits to the original during a run, not a malicious process with the
same operating-system identity. The existing agent
instructions still require human decisions on individual rows and review of
the resulting draft PR. Never merge maps or tests without human approval.
For local stdio specialists, the approved map must include a matching
`Build new test` or `Update assertion` row under `Human Review Required`.
Use semicolon-separated `key: value` entries in that row's Notes:

```text
track: security; planning: artifacts/test-strategy.md; target: path/to/local-checkout; fixture: path/to/local-checkout/test-fixtures/example.json; fixture-kind: synthetic; expected: allow and deny
```

Paths are relative to this repository. The planning artifact must exist; the
target must be a local Git checkout inside this workspace, and the fixture must
exist inside that checkout. `fixture-kind` must be `synthetic` or `local-mock`;
the human remains responsible for ensuring the fixture contains no real data.
For performance also provide `workload`, `warm-up` (non-negative count),
`sample-size` and `concurrency` (positive integers), `time-limit` (positive
integer with `s` or `m` suffix), `measurement`, `budget`, and `environment`.
The human-approved row must contain the actual acceptance criteria and limits;
the format check is not proof of their validity.

The stdio specialist runtime denies shell execution and writes, disables
upstream MCP servers, and does not request automatic approval. Consequently it
can inspect and report but **cannot create tests or run benchmarks**; perform
those actions in a human-controlled local Copilot session using the existing
specialist profile and permissions. This restriction prevents an unreviewed
MCP request from widening the approved fixture or executing remote work.
Copilot's programmatic `-p` mode cannot relay individual approval prompts.
ACP and the Copilot SDK can expose permission requests, and MCP elicitation
can ask supported clients for input, but an approval bridge alone does not
ensure generated tests are reviewed before execution or keep an approved shell
command on approved local fixtures. Copilot command sandboxing is disabled by
default and allows network access when first enabled; built-in edits are not
OS-sandboxed. A future bridge must fail closed when approval or sandbox support
is missing, enforce local-only execution and the approved limits, and require
review of the exact generated tests before allowing execution.
Incident RCA requires human confirmation before follow-on outputs; a response
requesting confirmation is not permission to proceed. These checks and the
agent instructions are not an authorization boundary against a malicious
caller or prompt injection; only trusted callers should be granted access.

Compose mounts `./knowledge` at `/app/knowledge`; supply approved maps there
and ensure the container user can read/write it. The Cloud Run example has
**ephemeral per-instance storage** and an in-memory A2A task store. It does
not contain a Git checkout or target repositories, and does not synchronize
approved maps, findings or generated artifacts with Git,
survive restarts, or provide a durable incident approval workflow. Before
production, provision a controlled shared workspace and durable task/approval
storage, limit write access to approved inputs, and decide how outputs are
reviewed and persisted. Do not use shared writable storage as a substitute
for an authorization boundary.

## Local stdio MCP

From the repository root, install the dependencies and authenticate Copilot
CLI for your eligible account:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r agent_service/requirements.txt
```

Merge the `qe-agents-local` entry from
[`agent_service/mcp-stdio.example.json`](../agent_service/mcp-stdio.example.json)
into your MCP client's project configuration without replacing existing
servers. Start the client with this repository as its workspace and working
directory; it launches `.venv/bin/python -m agent_service.stdio` on demand.
No HTTP listener or persistent service is needed. If the client does not
inherit authentication, configure it to pass a supported
`COPILOT_GITHUB_TOKEN` to the server. Keep the name `qe-agents-local`: child
Copilot runtimes disable that server, and a separate child-process guard also
prevents recursive starts if it is renamed.

Each tool accepts `{"task": "..."}`. Builder and specialist tasks include
`Story map: <workspace-relative-path>` on its own line. Specialists require the
decision row described above and `QE_AGENT_RUNTIME=copilot` (the default).
Only a trusted local user should run this server: stdio is a transport, not an
authorization boundary.

## Shared contract and result logs

The service validates requests and results with `AgentRequest` and
`AgentResult` in `agent_service/contracts.py`. MCP tools accept `task` and
optional UUID `run_id` and `parent_run_id`; a caller can use its own run ID as
the parent ID for each assigned agent. The result contains `schema_version`,
both IDs, `agent`, `status`, `mode`, `timestamp`, `output`, and `error`. MCP
returns this as structured content. A2A requests put optional IDs in message
`metadata`; successful artifacts contain the same result as JSON text. A
failed invocation is still reported as a protocol error or failed A2A task.
The contract wraps the agent's text; it does not validate its substantive claims.

Each service invocation records its result or failure in
`~/.qe-agent-service/agent-results.jsonl`. Set `QE_AGENT_LOG_DIR` to use
another private directory. Compose stores records in the `qe-agent-logs`
Docker volume; inspect them with:

```bash
docker compose exec -u qe qe-agents cat /home/qe/agent-logs/agent-results.jsonl
```

The log directory and file must be private; a logging failure is reported
instead of claiming the invocation succeeded. Inputs are not logged. Output
redaction covers certain PII and credential patterns, but is **not complete**:
use synthetic or already-masked inputs and outputs, restrict access, and
establish retention and secure storage before production. Logs in an
unmounted container or Cloud Run instance are ephemeral.

The service does not implement a separate orchestrator or intercept nested
subagents launched within Copilot, Claude, or the webhook receiver. Those
paths do not automatically use this contract or produce these result logs;
orchestrators must call the service and propagate the parent ID explicitly.

## Optional local HTTP

```bash
mkdir -p knowledge/findings knowledge/signals
export COPILOT_GITHUB_TOKEN='...'   # use your secret manager in production
docker compose up --build qe-agents
```

The service listens at `http://127.0.0.1:8083`. MCP Streamable HTTP is at
`/mcp`. Tool names are the agent file names with hyphens replaced by
underscores (for example `planning_agent`). Each takes `{"task": "..."}`.
For example, list the tools:

```bash
curl -X POST http://127.0.0.1:8083/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

For A2A 1.0, each agent has a card at
`/a2a/<agent-name>/.well-known/agent-card.json` and a JSON-RPC endpoint at
`/a2a/<agent-name>`. Cards advertise `QE_AGENT_BASE_URL` (default
`http://127.0.0.1:8083`); set it to the externally reachable service URL for
remote clients. A2A RPC requests require `X-QE-A2A-Key`, in addition to any
ingress credentials. Configure `QE_A2A_CLIENT_KEYS` as a JSON object mapping
each distinct client name to a distinct secret generated with
`secrets.token_urlsafe(32)`; store it in a secret manager, not source control.
Restart the service after changes. With no keys configured, A2A RPC requests
fail closed; agent cards remain available. Client names scope task history:
never share a key between callers. Cloud Run IAM authentication remains
mandatory and is separate from these keys. Do not rely on an unverified
identity header or expose HTTP MCP without its own ingress authorization.

The following non-streaming example assumes the caller has securely set
`QE_A2A_KEY` in its shell:

```bash
curl http://127.0.0.1:8083/a2a/planning-agent/.well-known/agent-card.json
printf 'header = "X-QE-A2A-Key: %s"\n' "$QE_A2A_KEY" | \
curl --config - -X POST http://127.0.0.1:8083/a2a/planning-agent \
  -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' \
  -d '{"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"messageId":"example-1","role":"ROLE_USER","parts":[{"text":"Analyse this synthetic requirement"}]}}}'
```

For offline protocol checks only, `QE_AGENT_MOCK=true` returns explicitly
labeled mock output without starting a model runtime. It does not bypass the builder
gate or the local-only specialist restriction. To run the live protocol tests
without credentials:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r agent_service/requirements.txt
.venv/bin/python -m unittest agent_service.tests.test_service -v
```

The tests launch the stdio command from the example configuration, start a
local HTTP service, list tools, fetch A2A cards and exercise approval gates.
They use mock execution; live requests require the credentials described above.

## Cloud Run

Create the Artifact Registry repository and the `copilot-github-token` Secret
Manager secret; give the runtime service account access to the secret. Adjust
`deploy/cloud-run/agents-service.yaml` to use your service account. It defaults
to internal ingress and requires IAM; widen ingress only behind an authenticated
gateway appropriate to your environment. To enable A2A RPC, separately mount
the `QE_A2A_CLIENT_KEYS` JSON from Secret Manager as an environment variable
and grant the service account access to it. Then run
`GCP_PROJECT_ID=... bash deploy/cloud-run/deploy-agents.sh`.
The script stages only the image's approved source inputs before upload, builds
a separate image and service without replacing the existing
webhook service, then configures the advertised URL. It does not grant public
access or remove existing IAM bindings: verify that neither `allUsers` nor
`allAuthenticatedUsers` can invoke an existing service. For an authorized client, attach a Cloud Run ID token in
`Authorization: Bearer <identity-token>` to MCP, card, and task requests.

Tasks execute synchronously with a default 240-second process timeout
(`QE_AGENT_TIMEOUT_SECONDS`); Cloud Run's example request timeout is 300
seconds. Instances serialize work, and MCP is stateless. There is no durable
queue, resumption, or cross-instance task history. Provisioning ingress, IAM,
upstream credentials, durable workspace and approval handling is required
before relying on this sample deployment.
