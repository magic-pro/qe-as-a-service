---
name: coverage-gap
description: Invoke the Coverage & Gap Analysis Agent. Scans GCP logs, OTEL traces, and production traffic against existing test coverage. Outputs a gap report, raises PRs to update .qe/ maps, and generates test creation requests. Run on a schedule or when new production signals are suspected.
---

Invoke the Coverage & Gap Analysis Agent as defined in `.claude/agents/coverage-agent.md`.

## Usage

```
/coverage-gap [--since <hours>] [--repo identity|microservices|both] [--layer <layer>]
```

Defaults: `--since 24` (last 24 hours), `--repo both`, all layers.

## Steps

1. Confirm the scan window and target repos with the user
2. Query GCP Log Explorer and OTEL via MCP tools for the scan period
3. Run all five analysis steps from the agent prompt
4. Write coverage gap report to `artifacts/coverage-gap-report.md`
5. Raise PRs on target repos for any map updates needed
6. Output structured test creation requests

## After Completion

Remind the user:
- Review `artifacts/coverage-gap-report.md`
- Review and merge any `.qe/` map update PRs on target repos
- For each test creation request: run `/create-tests` inside the affected target repo
- If new infra components found: re-run `/plan-analysis` to update `artifacts/infra-map.md`
