---
type: Design Spec
title: Test-Creator Agent — Local End-to-End Proof Harness
description: Design for proving the test-creator-agent runs end to end against a compilable Go payments fixture.
timestamp: 2026-05-30T00:00:00Z
status: approved
tags: [e2e, test-creator-agent, design]
---

# Test-Creator Agent — Local End-to-End Proof Harness

**Date:** 2026-05-30
**Author:** Planning / Solution Test Architecture
**Status:** Approved design — pending spec review

## Problem

The QEaaS framework defines a `test-creator-agent` that lives *inside* each target
repo, reads `.qe/data-type-map.md` + `.qe/identity-map.md`, examines existing tests,
and generates finance-safe tests. Today there is **no way to prove this loop actually
runs locally** — only templates (`repo-templates/`) and config stubs
(`target-repos/*.json` with `REPLACE_WITH_GITHUB_REPO_URL`) exist. There is no real
target repo with source + existing tests to run the agent against.

We need a repeatable, high-fidelity local proof that the creator agent runs
end-to-end, and a harness structured so the **same** proof generalizes to multiple
repo shapes (microservices and monorepos) and multiple stacks (Go now, pytest next).

## Goal

Prove the loop runs: scaffold a realistic target repo, invoke the **real** agent
headlessly via the `claude` CLI, and verify what it produces — including compiling
and running the generated tests.

### Success criteria

1. `claude -p --agent test-creator-agent` runs inside the fixture and exits 0.
2. The agent creates ≥1 new `*_test.go` file extending the existing suite.
3. Every new test function carries the mandatory traceability header
   (`BRD-REQ` / `JIRA` / `DATA-SCENARIO` / `INFRA-LAYER`).
4. No `float64` used for monetary values; `decimal.Decimal` throughout.
5. The agent **reuses** existing `helpers/` generators rather than duplicating them.
6. Coverage includes at least one amount-boundary scenario and one decimal-rounding
   scenario drawn from `.qe/data-type-map.md`.
7. **`go build ./... && go test ./...` pass** on the generated suite (Go toolchain
   installed for this run).

## Non-goals

- No PR / `workflow_dispatch` draft-PR path (that is the v2 in-repo workflow).
- No Planning Agent run — the `.qe/` maps are authored directly for the fixture.
- No production target repo wiring (`target-repos/*.json` stays as-is).

## Decisions (resolved)

| Decision | Choice |
|---|---|
| Primary goal | Prove the loop runs end-to-end |
| Sample target | Synthetic, realistic finance **Go microservice** |
| Run mode | Real headless `claude -p --agent test-creator-agent` |
| Test execution | **Install Go**, run `go build && go test` for real |
| Repo scope | Microservice fixture **now**; mono + pytest devcontainer **next** |

## Architecture

```
e2e/
├── run-creator-e2e.sh           # repo-agnostic runner: <target-dir>
├── verify-generated.sh          # structural conformance checks
├── fixtures/
│   └── payments-service/        # the sample target repo (a microservice)
│       ├── go.mod / go.sum
│       ├── payments/
│       │   ├── payment.go       # real ProcessPayment/ValidateAmount logic
│       │   └── payment_test.go  # one existing table-driven test (seed pattern)
│       ├── helpers/
│       │   └── synthetic_data.go# finance-safe generators (reused, not duplicated)
│       ├── .qe/
│       │   ├── data-type-map.md # transaction-scoped
│       │   └── identity-map.md  # auth-boundary slice
│       └── .claude/
│           └── agents/test-creator-agent.md  # copied from repo-templates
└── runs/<timestamp>/            # gitignored: run.log + report.md
```

### Component responsibilities

- **`fixtures/payments-service`** — a self-contained, compilable Go microservice.
  Its `payment.go` has genuine validation (reject zero/negative amount, enforce
  per-currency decimal places via a currency table, require IBAN on cross-border)
  so generated tests assert against real behaviour, not stubs. Source patterns are
  modeled on the existing `frameworks/golang/{helpers/finance.go,tests/payment_test.go}`.
- **`run-creator-e2e.sh <target-dir>`** —
  1. snapshot pre-run file list;
  2. `cd <target-dir>` and run the agent headlessly, capturing `run.log`;
  3. diff file list → list created/modified files;
  4. call `verify-generated.sh`;
  5. if Go present, `go build ./... && go test ./...`;
  6. write `report.md`.
- **`verify-generated.sh`** — greps the new test files for the success criteria
  (traceability headers, no `float64` near money, `helpers` import, boundary +
  rounding scenarios). Exit non-zero on any violation.

### Data flow

```
.qe/data-type-map.md ─┐
.qe/identity-map.md  ─┼─► test-creator-agent (claude -p) ─► new *_test.go files
existing *_test.go ──┘                                          │
helpers/synthetic_data.go ◄──────── reuse ─────────────────────┘
                                                                ▼
                                          go build && go test  +  verify-generated.sh
                                                                ▼
                                                         runs/<ts>/report.md
```

### Error handling

- `claude` non-zero exit → runner aborts, surfaces `run.log` tail.
- No new test files created → runner fails criterion 2 explicitly.
- `go` missing → runner fails fast with install guidance (for this run, Go is
  installed up front).
- Compile/test failure → report captures `go test` output; this is a real finding,
  not a harness bug.

## Repo-agnostic design (serves "multiple repos")

`run-creator-e2e.sh` takes the target directory as an argument and assumes only that
the target contains `.qe/` maps and `.claude/agents/test-creator-agent.md`. The
verification step is stack-aware (Go checks vs. pytest checks selected by a `--stack`
flag, default `go`). This is what lets Phase 2 reuse the same harness.

## Phase 2 (next — not this session)

- **Devcontainer + pytest target** modeled on `identity-repo` (Java/Groovy config +
  pytest integration tests), run inside a devcontainer for isolation — aligning with
  the devcontainers/sandbox theme of docker/desktop-feedback#227.
- **Monorepo fixture** (`services/payments` + `services/ledger`) to prove the loop on
  a mono layout using the same runner with a different target dir.

## Testing the harness itself

The harness is shell + a generated-code run. We validate it by: (a) a dry pre-run
that confirms `claude` and `go` are invocable; (b) asserting the runner correctly
reports zero new files if the agent is a no-op (negative path); (c) the real run
meeting all 7 success criteria.
