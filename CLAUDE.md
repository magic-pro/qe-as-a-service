# QEaaS — Quality Engineering as a Service

You are the orchestrator of a multi-agent Quality Engineering framework for a finance-sector product. Your role is the strategic layer: analyse requirements, produce sliced QE artifacts, and raise PRs that embed QE capability directly into each target repo (shift left).

## System Overview

```
qe-as-a-service/   ← YOU ARE HERE (strategic, external)
  Planning Agent   → produces sliced maps → PRs into target repos

identity-repo/     ← shift-left QE embedded here
  .qe/             ← maps scoped to identity/KYC/AML
  .claude/agents/  ← test-creator + test-healer agents

microservices-repo/ ← shift-left QE embedded here
  .qe/             ← maps scoped to transactions/data-integrity
  .claude/agents/  ← test-creator + test-healer agents
```

Signal sources connected via MCP servers (GitHub, Jira, Confluence, GCP, OTEL). v1: manual slash commands only.

## Agents (v1)

### Planning & Analysis Agent (lives here)
- **Invoke**: `/plan-analysis`
- **Input**: BRD, Jira story, architecture diagram (pasted or via MCP)
- **Output**:
  - `artifacts/test-strategy.md` — cross-cutting test strategy (stays here)
  - `artifacts/infra-map.md` — infrastructure complexity map (stays here)
  - PR on identity-repo: `.qe/data-type-map.md` (identity-scoped slice) + `.qe/identity-map.md` (full)
  - PR on microservices-repo: `.qe/data-type-map.md` (transaction-scoped slice) + `.qe/identity-map.md` (auth boundary slice)
- **Agent definition**: `.claude/agents/planning-agent.md`

### Test Creator Agent (lives inside each target repo)
- **Invoke**: `/create-tests` (run from within the target repo)
- **Input**: Reads `.qe/data-type-map.md` and `.qe/identity-map.md` from same repo
- **Output**: Test files added to existing test directories

### Test Healer Agent (lives inside each target repo)
- **Invoke**: `/heal-tests` or triggered by CI failure
- **Input**: Failing test output, CI logs
- **Output**: Fixed test PR raised on same repo

## Human Approval Gate

```
/plan-analysis → artifacts/ + PR on each target repo
                              ↓
                    [HUMAN REVIEWS .qe/ maps]
                              ↓
                         PR merged
                              ↓
                    /create-tests (inside target repo)
                              ↓
                    [HUMAN REVIEWS generated tests]
                              ↓
                    Tests committed to target repo
```

Never merge maps or tests to a target repo without explicit human approval.

## Shared Artifact Locations

| Artifact | Location | Scope | Written by |
|---|---|---|---|
| Test Strategy | `artifacts/test-strategy.md` | Cross-cutting | Planning Agent |
| Infra Map | `artifacts/infra-map.md` | Cross-cutting | Planning Agent |
| Data Type Map | `identity-repo/.qe/data-type-map.md` | Identity-scoped | Planning Agent (via PR) |
| Identity Map | `identity-repo/.qe/identity-map.md` | Full identity | Planning Agent (via PR) |
| Data Type Map | `microservices-repo/.qe/data-type-map.md` | Transaction-scoped | Planning Agent (via PR) |
| Identity Map | `microservices-repo/.qe/identity-map.md` | Auth boundary slice | Planning Agent (via PR) |

## Agents (v2 — Operational)

### Coverage & Gap Analysis Agent (lives here)
- **Invoke**: `/coverage-gap [--since <hours>] [--repo identity|microservices|both]`
- **Scheduled**: Nightly via `.github/workflows/nightly-coverage-scan.yml`
- **Input**: GCP Log Explorer, OTEL traces, existing test suites
- **Output**: `artifacts/coverage-gap-report.md`, PRs updating `.qe/` maps, test creation requests
- **Agent definition**: `.claude/agents/coverage-agent.md`

### Incident Analysis Agent (lives here)
- **Invoke**: `/incident-rca [--alert <url>] [--jira <id>]`
- **Input**: GCP alerts, OTEL traces, Jira incident tickets
- **Output**: Confirmed RCA, reproduction steps, auto-raised Jira/GitHub ticket, regression test request
- **Human gate**: Presents RCA for confirmation before generating outputs
- **Agent definition**: `.claude/agents/incident-agent.md`

## Agents (v3 — Fully Automated)

In v3, all agents are triggered automatically via the webhook receiver deployed on Cloud Run:

| Signal | Webhook | Agent triggered |
|---|---|---|
| GitHub PR with new service | `/webhooks/github` | Planning Agent |
| GitHub PR with dependency bump | `/webhooks/github` | Planning Agent |
| CI workflow failure | `/webhooks/github` | Coverage Agent + in-repo Healer |
| Jira story updated with AC | `/webhooks/jira` | Planning Agent |
| Jira story → In Development | `/webhooks/jira` | Planning Agent |
| High-priority Jira bug | `/webhooks/jira` | Incident Agent |
| Confluence BRD/ADR updated | `/webhooks/confluence` | Planning Agent |
| GCP Monitoring alert | `/webhooks/gcp-monitoring` | Incident Agent |

Deploy webhook receiver: `deploy/cloud-run/deploy.sh`

## Repo Templates

`repo-templates/` contains the agent definitions, map templates, and GHA workflows that are PR'd into each target repo on first setup:
- `.qe/` — scoped data type and identity maps
- `.claude/agents/` — test-creator and test-healer agent definitions
- `.github/workflows/qe-test-healer.yml` — auto-heal on CI failure (v2+)
- `.github/workflows/qe-create-tests-dispatched.yml` — `workflow_dispatch` entry point that lets the Coverage Agent and Incident Agent in this repo trigger the in-repo Test Creator headlessly with a structured `request_json` payload; the Test Creator raises a DRAFT PR that the developer reviews (the human approval gate stays on the PR)

## Finance-Specific Constraints (apply to ALL agents)

- **Monetary values**: always use `Decimal` type — never `float` or `double`
- **PII fields**: synthetic/masked data only — never real customer data in tests
- **Regulatory fields**: validated at every relevant layer (format, presence, value)
- **Audit trail**: completeness verified wherever applicable
- **KYC/AML flows**: treated as first-class test scenarios, not edge cases
- **Fraud signals**: velocity checks, pattern simulation included in test scope
- **Currency/locale/timezone**: variations covered where relevant
- **Boundary conditions**: all data type boundaries explicitly tested (null, empty, min, max, zero, negative, future-dated, duplicate)
- **Decimal precision**: monetary values tested to correct decimal places per currency
- **Regulatory impact**: flagged on all outputs where applicable

## MCP Servers

Configured in `.mcp.json`:
- **GitHub MCP** — `@modelcontextprotocol/server-github` (stdio). Set `GITHUB_PERSONAL_ACCESS_TOKEN`.
- **Atlassian MCP** — hosted SSE server (`https://mcp.atlassian.com/v1/sse`) covering both Jira and Confluence. Auth via Claude Code's `/mcp` OAuth flow.
- **GCP / OTEL** — not currently configured. No widely-available official MCP server exists for either. Agents must work from pasted log output / trace data / alert payloads until a custom MCP server is wired up.

## Target Repo Config

See `target-repos/identity-repo.json` and `target-repos/microservices-repo.json` for repo-specific paths, test frameworks, and CI config locations.