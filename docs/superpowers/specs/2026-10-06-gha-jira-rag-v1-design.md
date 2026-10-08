# GHA + JIRA + RAG v1 — Planning Agent First Working Version

## Status: approved for implementation

## Goal

Get the Planning Agent running end-to-end via GitHub Actions, fetching context from JIRA REST API and autogentests RAG, with a Docker Compose mock layer for local dev and CI validation.

## Architecture

```
Local dev                              GHA (CI)
──────────────────────────────         ─────────────────────────────────────
docker compose up -d                   workflow_dispatch (jira_key input)
  mock-jira (WireMock :8081)             docker compose up -d mock-jira mock-autogentests
  mock-autogentests (FastAPI :8082)      anthropics/claude-code-action@v1
        ↓                                       ↓
claude --agent planning-agent          Same agent, same fetch-first preamble
  JIRA_KEY=ABC-123                     JIRA_KEY from workflow input
  JIRA_BASE_URL=http://localhost:8081  URLs point to localhost mock services
  AUTOGENTESTS_URL=http://localhost:8082
```

Real vs mock is controlled by `USE_MOCKS=true/false` + URL swap only. Agent code is identical in both paths.

## New Files

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Defines mock-jira and mock-autogentests services |
| `docker-compose.mock.yml` | Override: replaces real autogentests with mock stub |
| `mocks/jira/mappings/kyc-story-ABC-123.json` | WireMock stub — KYC onboarding story |
| `mocks/jira/mappings/payment-story-PAY-456.json` | WireMock stub — payment processing story |
| `mocks/jira/__files/` | Large response bodies served by WireMock by reference |
| `mocks/autogentests/main.py` | FastAPI stub — same interface as real wrapper, canned fixtures |
| `mocks/autogentests/Dockerfile` | Build for mock autogentests service |
| `mocks/autogentests/fixtures/identity-patterns.json` | Canned RAG response for identity domain |
| `mocks/autogentests/fixtures/payments-patterns.json` | Canned RAG response for payments domain |
| `mocks/autogentests/fixtures/general-patterns.json` | Canned RAG response fallback |
| `.github/workflows/planning-agent-jira.yml` | New GHA workflow — workflow_dispatch with jira_key input |

## Modified Files

| Path | Change |
|---|---|
| `.claude/agents/planning-agent.md` | Add Step -1: fetch JIRA story + query autogentests before any analysis |

## Autogentests Mock Interface

```
POST /query
Body:  { "query": str, "domain": str, "context": {} }
Response: { "patterns": [...], "constraints": [...], "prior_analyses": [...] }

GET /health
Response: { "status": "ok" }
```

The real autogentests wrapper (to be built in autogentests repo, v2) will expose the identical interface. The planning agent calls it the same way regardless.

## JIRA Endpoints Used

```
GET /rest/api/3/issue/{key}             → story detail
GET /rest/api/3/issue/{key}/remotelink  → linked BRD / Confluence page
GET /rest/api/3/search?jql=...          → epic children (optional, for multi-story context)
```

Auth: `Authorization: Basic $JIRA_TOKEN` (base64 of `email:api_token`).

## Planning Agent Fetch-First Preamble

Added as Step -1 to `planning-agent.md`, before all existing analysis steps:

1. `curl` JIRA story using `JIRA_BASE_URL` + `JIRA_KEY` env vars
2. Derive domain from epic/labels (identity → "identity", payments → "payments", else "general")
3. `curl` autogentests `POST /query` with story summary + domain
4. Use fetched story + RAG patterns as working context — never require context pasted in prompt

## GHA Workflow

File: `.github/workflows/planning-agent-jira.yml`

- Trigger: `workflow_dispatch` with `jira_key` (required) and `use_mocks` (default: true) inputs
- When `use_mocks=true`: starts Docker Compose mock services before claude-code-action step
- Uses `anthropics/claude-code-action@v1`
- Injects: `JIRA_KEY`, `JIRA_BASE_URL`, `JIRA_TOKEN`, `AUTOGENTESTS_URL` as env vars
- URL switching: localhost for mocks, secrets for real

## Mock Fixture Shape

`identity-patterns.json`:
```json
{
  "patterns": [
    "KYC identity verification must check document expiry",
    "AML screening required for all new customer onboarding",
    "PEP/sanctions check is a first-class test scenario"
  ],
  "constraints": [
    "PII fields: synthetic data only",
    "Document numbers: masked format NNN-XXXX-NNN"
  ],
  "prior_analyses": []
}
```

## Finance Constraints (unchanged from CLAUDE.md)

All planning agent finance constraints apply — Decimal types, PII masking, KYC/AML first-class, regulatory fields validated at every layer.

## Out of Scope (v1)

- Real autogentests HTTP wrapper (v2 — builds in autogentests repo)
- Real Jira webhook trigger (v2 — `repository_dispatch` from webhook receiver)
- Confluence / BRD fetching
- PR raised against target repos (agent produces maps locally; PR step is manual in v1)
