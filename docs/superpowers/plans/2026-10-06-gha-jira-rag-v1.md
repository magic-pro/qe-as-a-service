# GHA + JIRA + RAG v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the Planning Agent running end-to-end in GitHub Actions, fetching context from JIRA REST API and autogentests RAG, with a Docker Compose mock layer for local dev and CI.

**Architecture:** Two Docker Compose mock services (WireMock for JIRA, FastAPI stub for autogentests) run locally and in GHA. The planning agent is updated with a fetch-first preamble (Step -1) that pulls JIRA story + RAG patterns via env vars before any analysis. GHA workflow triggers via `workflow_dispatch` with a `jira_key` input and starts mock services before invoking the agent.

**Tech Stack:** WireMock 3.x (Docker), FastAPI + uvicorn (Python 3.12), Docker Compose v2, GitHub Actions, Claude Code CLI (`@anthropic-ai/claude-code`), `anthropics/claude-code-action@v1`

**Spec:** `docs/superpowers/specs/2026-10-06-gha-jira-rag-v1-design.md`

## Global Constraints

- Python 3.12 (matches existing Dockerfile)
- WireMock image: `wiremock/wiremock:3.10.0`
- FastAPI stubs must expose identical interface to real autogentests wrapper
- Finance constraints from CLAUDE.md apply to all fixture data — synthetic PII only, no real customer data
- Never `float` for monetary values in fixtures — use strings (`"amount": "1234.56"`)
- Mock JIRA responses must include `labels` array to allow domain derivation by the agent
- All env vars (`JIRA_BASE_URL`, `JIRA_KEY`, `JIRA_TOKEN`, `AUTOGENTESTS_URL`) are required — agent fails clearly if missing

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `mocks/autogentests/main.py` | Create | FastAPI stub — POST /query + GET /health |
| `mocks/autogentests/Dockerfile` | Create | Build stub service |
| `mocks/autogentests/requirements.txt` | Create | fastapi + uvicorn |
| `mocks/autogentests/fixtures/identity-patterns.json` | Create | Canned RAG response for identity domain |
| `mocks/autogentests/fixtures/payments-patterns.json` | Create | Canned RAG response for payments domain |
| `mocks/autogentests/fixtures/general-patterns.json` | Create | Canned RAG response fallback |
| `mocks/jira/mappings/kyc-story-ABC-123.json` | Create | WireMock stub — GET /rest/api/3/issue/ABC-123 |
| `mocks/jira/mappings/kyc-story-remotelink.json` | Create | WireMock stub — GET /rest/api/3/issue/ABC-123/remotelink |
| `mocks/jira/mappings/payment-story-PAY-456.json` | Create | WireMock stub — GET /rest/api/3/issue/PAY-456 |
| `mocks/jira/mappings/payment-story-remotelink.json` | Create | WireMock stub — GET /rest/api/3/issue/PAY-456/remotelink |
| `mocks/jira/__files/kyc-story-body.json` | Create | Full JIRA API v3 response body for ABC-123 |
| `mocks/jira/__files/payment-story-body.json` | Create | Full JIRA API v3 response body for PAY-456 |
| `docker-compose.yml` | Create | mock-jira + mock-autogentests services |
| `docker-compose.mock.yml` | Create | Override file (documents v2 real→mock swap pattern) |
| `.github/workflows/planning-agent-jira.yml` | Create | GHA workflow — workflow_dispatch + mock services + agent |
| `.claude/agents/planning-agent.md` | Modify | Add Step -1: fetch-first preamble before existing Analysis Steps |

---

### Task 1: Mock autogentests FastAPI stub

**Files:**
- Create: `mocks/autogentests/main.py`
- Create: `mocks/autogentests/Dockerfile`
- Create: `mocks/autogentests/requirements.txt`
- Create: `mocks/autogentests/fixtures/identity-patterns.json`
- Create: `mocks/autogentests/fixtures/payments-patterns.json`
- Create: `mocks/autogentests/fixtures/general-patterns.json`

**Interfaces:**
- Produces: `POST http://localhost:8082/query` → `{"patterns":[...], "constraints":[...], "prior_analyses":[...]}`
- Produces: `GET http://localhost:8082/health` → `{"status":"ok"}`
- Consumed by: Task 3 (docker-compose.yml), Task 4 (planning-agent Step -1)

- [ ] **Step 1: Create identity fixture**

```json
// mocks/autogentests/fixtures/identity-patterns.json
{
  "patterns": [
    "KYC identity verification must check document expiry date",
    "AML screening required before account activation for all new customers",
    "PEP and sanctions list check is a first-class test scenario, not an edge case",
    "Document upload must validate file type (passport, driving licence, utility bill)",
    "Re-verification required if document expires within 30 days"
  ],
  "constraints": [
    "PII fields must use synthetic data only — never real document numbers",
    "Document numbers: masked format NNN-XXXX-NNN in all test fixtures",
    "Date of birth: must be ≥18 years in the past for all valid-customer scenarios",
    "Address fields: use Royal Mail PAF-compliant synthetic addresses"
  ],
  "prior_analyses": []
}
```

- [ ] **Step 2: Create payments fixture**

```json
// mocks/autogentests/fixtures/payments-patterns.json
{
  "patterns": [
    "Monetary amounts must use Decimal type — never float or double",
    "Payment amount boundary conditions: zero, negative, minimum (0.01), maximum per-currency limit",
    "Duplicate payment detection: same amount + recipient + timestamp within 60s window",
    "Currency mismatch between source account and payment currency must be handled explicitly",
    "SWIFT/SEPA reference codes must be validated against format regex",
    "Velocity checks: flag >3 payments to new payee within 24h as fraud signal"
  ],
  "constraints": [
    "Monetary amounts: Decimal(precision=19, scale=4) — test to 4 decimal places",
    "Currency codes: ISO 4217 only (GBP, EUR, USD, AUD)",
    "Account numbers: synthetic BSB/sort-code format only",
    "Transaction IDs: UUID v4 format in all fixtures"
  ],
  "prior_analyses": []
}
```

- [ ] **Step 3: Create general fallback fixture**

```json
// mocks/autogentests/fixtures/general-patterns.json
{
  "patterns": [
    "All API endpoints require authentication token validation",
    "Audit log entries must include: actor, action, resource, timestamp, outcome",
    "Regulatory fields must be validated at every service boundary",
    "Null and empty string must be treated as distinct values in all validation logic"
  ],
  "constraints": [
    "Timestamps: ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)",
    "All monetary values: Decimal — never float",
    "PII fields: synthetic data only"
  ],
  "prior_analyses": []
}
```

- [ ] **Step 4: Create FastAPI stub**

```python
# mocks/autogentests/main.py
import json
import pathlib
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="autogentests-mock")
FIXTURES = pathlib.Path(__file__).parent / "fixtures"

class QueryRequest(BaseModel):
    query: str
    domain: str = "general"
    context: dict = {}

@app.post("/query")
async def query(req: QueryRequest):
    fixture = FIXTURES / f"{req.domain}-patterns.json"
    if not fixture.exists():
        fixture = FIXTURES / "general-patterns.json"
    return json.loads(fixture.read_text())

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Create requirements.txt**

```
# mocks/autogentests/requirements.txt
fastapi==0.115.0
uvicorn==0.30.6
pydantic==2.9.0
```

- [ ] **Step 6: Create Dockerfile**

```dockerfile
# mocks/autogentests/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 7: Build and smoke-test the stub locally**

```bash
cd mocks/autogentests
docker build -t mock-autogentests .
docker run -d -p 8082:8000 --name mock-autogentests-test mock-autogentests
sleep 2

# Health check
curl -s http://localhost:8082/health
# Expected: {"status":"ok"}

# Query identity domain
curl -s -X POST http://localhost:8082/query \
  -H "Content-Type: application/json" \
  -d '{"query": "KYC document verification", "domain": "identity"}'
# Expected: {"patterns":[...], "constraints":[...], "prior_analyses":[]}

# Query unknown domain — should fall back to general
curl -s -X POST http://localhost:8082/query \
  -H "Content-Type: application/json" \
  -d '{"query": "something else", "domain": "risk"}'
# Expected: general-patterns.json content

docker rm -f mock-autogentests-test
cd ../..
```

- [ ] **Step 8: Commit**

```bash
git add mocks/autogentests/
git commit -m "feat(mocks): autogentests FastAPI stub with identity/payments/general fixtures"
```

---

### Task 2: Mock JIRA (WireMock) stubs

**Files:**
- Create: `mocks/jira/__files/kyc-story-body.json`
- Create: `mocks/jira/__files/payment-story-body.json`
- Create: `mocks/jira/__files/kyc-story-remotelink-body.json`
- Create: `mocks/jira/__files/payment-story-remotelink-body.json`
- Create: `mocks/jira/mappings/kyc-story-ABC-123.json`
- Create: `mocks/jira/mappings/kyc-story-remotelink.json`
- Create: `mocks/jira/mappings/payment-story-PAY-456.json`
- Create: `mocks/jira/mappings/payment-story-remotelink.json`

**Interfaces:**
- Produces: `GET http://localhost:8081/rest/api/3/issue/ABC-123` → KYC story JSON
- Produces: `GET http://localhost:8081/rest/api/3/issue/ABC-123/remotelink` → BRD link JSON
- Produces: `GET http://localhost:8081/rest/api/3/issue/PAY-456` → payment story JSON
- Produces: `GET http://localhost:8081/rest/api/3/issue/PAY-456/remotelink` → BRD link JSON
- Consumed by: Task 3 (docker-compose.yml), Task 4 (planning-agent Step -1)

- [ ] **Step 1: Create KYC story response body**

```json
// mocks/jira/__files/kyc-story-body.json
{
  "id": "10001",
  "key": "ABC-123",
  "self": "http://localhost:8081/rest/api/3/issue/10001",
  "fields": {
    "summary": "KYC Identity Verification — Document Upload and IDV Flow",
    "issuetype": { "name": "Story" },
    "status": { "name": "In Progress" },
    "priority": { "name": "High" },
    "labels": ["identity", "kyc", "aml", "compliance"],
    "customfield_10014": "ABC-120",
    "description": {
      "type": "doc",
      "version": 1,
      "content": [
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "As a new customer, I need to upload identity documents and complete IDV so that my account can be activated in compliance with KYC regulations."
            }
          ]
        },
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "Acceptance Criteria: 1) Passport and driving licence accepted. 2) Documents expire >30 days from upload date. 3) AML screening completes within 5 seconds. 4) PEP/sanctions check performed on all new customers. 5) Failed IDV shows clear error with retry option. 6) Audit log entry created for every verification attempt."
            }
          ]
        }
      ]
    },
    "assignee": { "displayName": "Dev User" },
    "reporter": { "displayName": "Product Owner" },
    "created": "2026-09-15T09:00:00.000+0000",
    "updated": "2026-10-01T14:22:00.000+0000"
  }
}
```

- [ ] **Step 2: Create KYC remotelink body**

```json
// mocks/jira/__files/kyc-story-remotelink-body.json
[
  {
    "id": 1001,
    "self": "http://localhost:8081/rest/api/3/issue/ABC-123/remotelink/1001",
    "object": {
      "url": "https://confluence.example.com/display/BRD/KYC-2026",
      "title": "KYC Identity Verification BRD — 2026",
      "summary": "Business Requirements Document for KYC identity verification flow including IDV provider integration, AML screening, and PEP/sanctions checks.",
      "icon": {
        "url16x16": "https://confluence.example.com/favicon.ico",
        "title": "Confluence"
      }
    }
  }
]
```

- [ ] **Step 3: Create payment story response body**

```json
// mocks/jira/__files/payment-story-body.json
{
  "id": "10002",
  "key": "PAY-456",
  "self": "http://localhost:8081/rest/api/3/issue/10002",
  "fields": {
    "summary": "Domestic Payment Processing — CHAPS and Faster Payments",
    "issuetype": { "name": "Story" },
    "status": { "name": "To Do" },
    "priority": { "name": "Critical" },
    "labels": ["payments", "transaction", "chaps", "faster-payments", "regulatory"],
    "customfield_10014": "PAY-400",
    "description": {
      "type": "doc",
      "version": 1,
      "content": [
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "As a customer, I need to send domestic payments via CHAPS and Faster Payments so that funds arrive same-day or within 2 hours."
            }
          ]
        },
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "Acceptance Criteria: 1) Payments up to GBP 250,000 via CHAPS. 2) Faster Payments up to GBP 100,000. 3) Duplicate payment detection within 60-second window. 4) Velocity check: >3 payments to new payee in 24h triggers fraud flag. 5) All monetary amounts stored as Decimal (not float). 6) Payment reference validated against Faster Payments regex. 7) Audit trail entry for every payment state transition."
            }
          ]
        }
      ]
    },
    "assignee": { "displayName": "Payments Dev" },
    "reporter": { "displayName": "Payments PO" },
    "created": "2026-09-20T10:00:00.000+0000",
    "updated": "2026-10-03T11:00:00.000+0000"
  }
}
```

- [ ] **Step 4: Create payment remotelink body**

```json
// mocks/jira/__files/payment-story-remotelink-body.json
[
  {
    "id": 1002,
    "self": "http://localhost:8081/rest/api/3/issue/PAY-456/remotelink/1002",
    "object": {
      "url": "https://confluence.example.com/display/BRD/PAY-2026",
      "title": "Domestic Payments BRD — CHAPS and Faster Payments 2026",
      "summary": "Business Requirements Document for domestic payment processing including CHAPS, Faster Payments, velocity checks, and fraud detection.",
      "icon": {
        "url16x16": "https://confluence.example.com/favicon.ico",
        "title": "Confluence"
      }
    }
  }
]
```

- [ ] **Step 5: Create WireMock mapping for ABC-123 story**

```json
// mocks/jira/mappings/kyc-story-ABC-123.json
{
  "request": {
    "method": "GET",
    "url": "/rest/api/3/issue/ABC-123"
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "bodyFileName": "kyc-story-body.json"
  }
}
```

- [ ] **Step 6: Create WireMock mapping for ABC-123 remotelink**

```json
// mocks/jira/mappings/kyc-story-remotelink.json
{
  "request": {
    "method": "GET",
    "url": "/rest/api/3/issue/ABC-123/remotelink"
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "bodyFileName": "kyc-story-remotelink-body.json"
  }
}
```

- [ ] **Step 7: Create WireMock mapping for PAY-456 story**

```json
// mocks/jira/mappings/payment-story-PAY-456.json
{
  "request": {
    "method": "GET",
    "url": "/rest/api/3/issue/PAY-456"
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "bodyFileName": "payment-story-body.json"
  }
}
```

- [ ] **Step 8: Create WireMock mapping for PAY-456 remotelink**

```json
// mocks/jira/mappings/payment-story-remotelink.json
{
  "request": {
    "method": "GET",
    "url": "/rest/api/3/issue/PAY-456/remotelink"
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "bodyFileName": "payment-story-remotelink-body.json"
  }
}
```

- [ ] **Step 9: Smoke-test WireMock stubs**

```bash
docker run -d -p 8081:8080 --name mock-jira-test \
  -v $(pwd)/mocks/jira:/home/wiremock \
  wiremock/wiremock:3.10.0

sleep 3

# Fetch KYC story
curl -s http://localhost:8081/rest/api/3/issue/ABC-123 | python3 -m json.tool | head -20
# Expected: key = "ABC-123", labels includes "identity"

# Fetch payment story
curl -s http://localhost:8081/rest/api/3/issue/PAY-456 | python3 -m json.tool | head -20
# Expected: key = "PAY-456", labels includes "payments"

# Fetch remotelink
curl -s http://localhost:8081/rest/api/3/issue/ABC-123/remotelink | python3 -m json.tool
# Expected: array with confluence BRD link

# Unknown issue key returns 404
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/rest/api/3/issue/UNKNOWN-999
# Expected: 404

docker rm -f mock-jira-test
```

- [ ] **Step 10: Commit**

```bash
git add mocks/jira/
git commit -m "feat(mocks): WireMock stubs for KYC (ABC-123) and payments (PAY-456) JIRA stories"
```

---

### Task 3: Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.mock.yml`

**Interfaces:**
- Consumes: `mocks/jira/` (Task 2), `mocks/autogentests/` (Task 1)
- Produces: `mock-jira` on `localhost:8081`, `mock-autogentests` on `localhost:8082`
- Consumed by: Task 4 (local dev run), Task 5 (GHA workflow)

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# docker-compose.yml
services:
  mock-jira:
    image: wiremock/wiremock:3.10.0
    volumes:
      - ./mocks/jira:/home/wiremock
    ports:
      - "8081:8080"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/__admin/health || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10

  mock-autogentests:
    build: ./mocks/autogentests
    ports:
      - "8082:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10
```

- [ ] **Step 2: Create docker-compose.mock.yml**

```yaml
# docker-compose.mock.yml
# Override file: swap real autogentests service for mock stub.
# Usage: docker compose -f docker-compose.yml -f docker-compose.mock.yml up -d
#
# In v1 both services in docker-compose.yml are already mocks.
# This override becomes relevant in v2 when docker-compose.yml points to the
# real autogentests wrapper (build: ../autogentests) — run this override in CI
# to restore mock behaviour without changing docker-compose.yml.
services:
  mock-autogentests:
    build: ./mocks/autogentests
    ports:
      - "8082:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10
```

- [ ] **Step 3: Bring up both services and verify**

```bash
docker compose up -d

# Wait for healthy
docker compose ps
# Both services should show "healthy" or "running"

# Verify mock-jira
curl -s http://localhost:8081/rest/api/3/issue/ABC-123 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['key'])"
# Expected: ABC-123

# Verify mock-autogentests
curl -s http://localhost:8082/health
# Expected: {"status":"ok"}

docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.mock.yml
git commit -m "feat: docker-compose with mock-jira (WireMock) and mock-autogentests services"
```

---

### Task 4: Planning agent fetch-first preamble (Step -1)

**Files:**
- Modify: `.claude/agents/planning-agent.md`

**Interfaces:**
- Consumes: `JIRA_BASE_URL`, `JIRA_KEY`, `JIRA_TOKEN`, `AUTOGENTESTS_URL` env vars
- Consumes: `GET $JIRA_BASE_URL/rest/api/3/issue/$JIRA_KEY` (Task 2 mock or real JIRA)
- Consumes: `POST $AUTOGENTESTS_URL/query` (Task 1 mock or real autogentests)
- Produces: fetched story context + RAG patterns used in Steps 0–5

- [ ] **Step 1: Read the current planning-agent.md to find the insertion point**

Open `.claude/agents/planning-agent.md`. Find the line:
```
## Analysis Steps
```
The new Step -1 block goes **immediately before** `## Analysis Steps`.

- [ ] **Step 2: Insert the fetch-first preamble**

Insert the following block directly before `## Analysis Steps`:

```markdown
## Step -1: Context Fetch (always run first)

Before any analysis, fetch live context via bash. These four env vars are required — stop and report clearly if any are missing:
- `JIRA_BASE_URL` — e.g. `https://your-org.atlassian.net` (or `http://localhost:8081` for mocks)
- `JIRA_KEY` — e.g. `ABC-123`
- `JIRA_TOKEN` — base64 of `email:api_token` for JIRA Basic auth
- `AUTOGENTESTS_URL` — e.g. `http://localhost:8082`

**1. Fetch JIRA story:**
```bash
curl -s \
  -H "Authorization: Basic $JIRA_TOKEN" \
  -H "Content-Type: application/json" \
  "$JIRA_BASE_URL/rest/api/3/issue/$JIRA_KEY"
```
Extract from `fields`: `summary`, `description` (flatten ADF content to plain text), `labels`, `priority.name`, `customfield_10014` (epic link).

**2. Fetch linked BRD:**
```bash
curl -s \
  -H "Authorization: Basic $JIRA_TOKEN" \
  -H "Content-Type: application/json" \
  "$JIRA_BASE_URL/rest/api/3/issue/$JIRA_KEY/remotelink"
```
Extract: first `object.url` and `object.title` (the linked Confluence BRD page). Use as traceability reference in artifacts.

**3. Derive domain** from `fields.labels`:
- Any of `[identity, kyc, aml, auth, idv]` → domain = `"identity"`
- Any of `[payments, transaction, transfer, chaps, faster-payments]` → domain = `"payments"`
- Otherwise → domain = `"general"`

**4. Query autogentests RAG:**
```bash
curl -s -X POST "$AUTOGENTESTS_URL/query" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"<story summary>\", \"domain\": \"<derived domain>\", \"context\": {}}"
```
Substitute `<story summary>` with `fields.summary` from step 1. Extract `patterns`, `constraints`, `prior_analyses` from the response.

**5. Use fetched context** as your working input for Steps 0–5. Never require the Jira story or BRD content to be pasted into the prompt. If either fetch fails (non-200 response), log the URL + status code and continue with available data.
```

- [ ] **Step 3: Verify the edit looks correct**

Read `.claude/agents/planning-agent.md` and confirm:
- Step -1 block appears before `## Analysis Steps`
- The four env vars are listed with correct names
- The three curl commands are present with correct URLs
- No existing steps were shifted or corrupted

- [ ] **Step 4: Local end-to-end smoke test**

Start mock services, then run the agent with mock env vars:
```bash
docker compose up -d

# Wait for healthy
sleep 5

# Run agent — use a dummy JIRA_TOKEN (WireMock doesn't check auth)
JIRA_BASE_URL=http://localhost:8081 \
JIRA_KEY=ABC-123 \
JIRA_TOKEN=dXNlcjpwYXNz \
AUTOGENTESTS_URL=http://localhost:8082 \
claude --agent planning-agent "Analyse Jira story ABC-123 and produce QE maps."
```

Expected agent behaviour:
- Agent fetches `http://localhost:8081/rest/api/3/issue/ABC-123` — returns KYC story JSON
- Agent fetches `http://localhost:8081/rest/api/3/issue/ABC-123/remotelink` — returns BRD link
- Agent derives domain `"identity"` from labels `["identity", "kyc", "aml", "compliance"]`
- Agent queries `http://localhost:8082/query` with `{"query": "KYC Identity Verification...", "domain": "identity"}`
- Agent proceeds to produce `artifacts/test-strategy.md`, `artifacts/infra-map.md`, and maps

```bash
docker compose down
```

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/planning-agent.md
git commit -m "feat(agent): add Step -1 fetch-first preamble — JIRA REST + autogentests RAG before analysis"
```

---

### Task 5: GHA workflow

**Files:**
- Create: `.github/workflows/planning-agent-jira.yml`

**Interfaces:**
- Consumes: `ANTHROPIC_API_KEY` (GHA secret), `JIRA_TOKEN` (GHA secret), `JIRA_BASE_URL` (GHA secret, used when `use_mocks=false`)
- Consumes: `workflow_dispatch` inputs: `jira_key` (required), `use_mocks` (default: `true`)
- Produces: agent run that fetches JIRA + RAG and writes QE map artifacts to the workspace

Note on `claude-code-action`: the action handles Claude Code installation and invocation. Check the latest version at https://github.com/anthropics/claude-code-action before running — update `@v1` if a newer stable release exists.

- [ ] **Step 1: Create the workflow file**

```yaml
# .github/workflows/planning-agent-jira.yml
name: QEaaS — Planning Agent (JIRA trigger)

on:
  workflow_dispatch:
    inputs:
      jira_key:
        description: 'Jira story key to analyse (e.g. ABC-123)'
        required: true
      use_mocks:
        description: 'Use mock JIRA + autogentests services'
        required: false
        default: 'true'

jobs:
  plan:
    name: Planning Agent — ${{ github.event.inputs.jira_key }}
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Start mock services
        if: github.event.inputs.use_mocks == 'true'
        run: |
          docker compose up -d
          echo "Waiting for mock services to be healthy..."
          timeout 60 bash -c '
            until curl -sf http://localhost:8081/__admin/health && curl -sf http://localhost:8082/health; do
              echo "  still waiting..."
              sleep 3
            done
          '
          echo "Mock services ready."

      - name: Run Planning Agent
        uses: anthropics/claude-code-action@v1
        with:
          prompt: >
            Analyse Jira story ${{ github.event.inputs.jira_key }} and produce all four QE artifacts.
            Use Step -1 to fetch the story and RAG context first.
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
        env:
          JIRA_KEY: ${{ github.event.inputs.jira_key }}
          JIRA_BASE_URL: ${{ github.event.inputs.use_mocks == 'true' && 'http://localhost:8081' || secrets.JIRA_BASE_URL }}
          JIRA_TOKEN: ${{ github.event.inputs.use_mocks == 'true' && 'dXNlcjpwYXNz' || secrets.JIRA_TOKEN }}
          AUTOGENTESTS_URL: ${{ github.event.inputs.use_mocks == 'true' && 'http://localhost:8082' || secrets.AUTOGENTESTS_URL }}

      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: qe-maps-${{ github.event.inputs.jira_key }}-${{ github.run_id }}
          path: |
            artifacts/test-strategy.md
            artifacts/infra-map.md
          retention-days: 30

      - name: Post summary
        if: always()
        run: |
          echo "## QEaaS Planning Agent — ${{ github.event.inputs.jira_key }}" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          if [ -f artifacts/test-strategy.md ]; then
            echo "### Test Strategy" >> $GITHUB_STEP_SUMMARY
            head -80 artifacts/test-strategy.md >> $GITHUB_STEP_SUMMARY
          else
            echo "No test-strategy.md produced." >> $GITHUB_STEP_SUMMARY
          fi

      - name: Stop mock services
        if: always() && github.event.inputs.use_mocks == 'true'
        run: docker compose down
```

- [ ] **Step 2: Verify GHA expression syntax for env vars**

The inline ternary `${{ condition && 'value' || secrets.X }}` is valid GHA expression syntax but only works when the false branch is a secret. Verify this works in your GHA environment by running the workflow manually with `use_mocks=true` first.

If the GHA expression doesn't evaluate as expected, replace with an explicit step:

```yaml
      - name: Set service URLs
        id: urls
        run: |
          if [ "${{ github.event.inputs.use_mocks }}" = "true" ]; then
            echo "jira_url=http://localhost:8081" >> $GITHUB_OUTPUT
            echo "autogentests_url=http://localhost:8082" >> $GITHUB_OUTPUT
            echo "jira_token=dXNlcjpwYXNz" >> $GITHUB_OUTPUT
          else
            echo "jira_url=${{ secrets.JIRA_BASE_URL }}" >> $GITHUB_OUTPUT
            echo "autogentests_url=${{ secrets.AUTOGENTESTS_URL }}" >> $GITHUB_OUTPUT
            echo "jira_token=${{ secrets.JIRA_TOKEN }}" >> $GITHUB_OUTPUT
          fi
```
Then reference `${{ steps.urls.outputs.jira_url }}` etc. in the agent step.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/planning-agent-jira.yml
git commit -m "feat(ci): GHA workflow for Planning Agent — workflow_dispatch with mock JIRA + RAG"
```

- [ ] **Step 4: First GHA run**

Push the branch, go to GitHub → Actions → "QEaaS — Planning Agent (JIRA trigger)" → Run workflow.
Inputs: `jira_key = ABC-123`, `use_mocks = true`.

Verify in the workflow log:
1. Mock services start and become healthy
2. Agent step runs and calls `http://localhost:8081/rest/api/3/issue/ABC-123`
3. Agent calls `http://localhost:8082/query`
4. `artifacts/test-strategy.md` appears in the uploaded artifacts

- [ ] **Step 5: Commit any fixes found during first run**

```bash
git add -p
git commit -m "fix(ci): <describe what needed fixing after first GHA run>"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Task 1 covers autogentests mock; Task 2 covers JIRA WireMock; Task 3 covers docker-compose; Task 4 covers planning-agent preamble; Task 5 covers GHA workflow. All spec sections covered.
- [x] **No placeholders:** All steps contain actual file content, commands, and expected outputs.
- [x] **Type consistency:** `QueryRequest.domain` used consistently as `str` across all tasks. Fixture filenames consistent: `{domain}-patterns.json`.
- [x] **Finance constraints:** Fixture data uses string amounts (`"1234.56"`), synthetic PII only, no real document numbers.
- [x] **Out-of-scope respected:** No real autogentests wrapper, no Confluence fetching, no auto-PR to target repos — all correctly omitted.
