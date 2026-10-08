---
type: Index
title: QEaaS knowledge bundle
description: Entry point to everything QEaaS knows — inbound signals, agent findings, cross-cutting artifacts, per-repo maps and the agents themselves.
tags: [okf, index]
---

# QEaaS knowledge bundle

This is the OKF entry point, so agents should read it first. The conventions are in [okf/conventions.md](../okf/conventions.md).

## Live knowledge (written by the pipeline)

- [Signals](signals/index.md): one normalised doc per Jira, GitHub or GCP event
- [Findings](findings/index.md): agent outputs, each with `derived_from` pointing at a signal

## Cross-cutting knowledge

- [Artifacts](../artifacts/index.md): test strategy and infrastructure map
- [Docs](../docs/index.md): architecture, design specs and plans
- [Change log](../log.md)

## Per-repo bundles (`.qe/`)

- [identity-repo template](../repo-templates/identity-repo/.qe/index.md)
- [microservices-repo template](../repo-templates/microservices-repo/.qe/index.md)
- [payments-service E2E fixture](../e2e/fixtures/payments-service/.qe/index.md)

## Agents

| Agent | Consumes | Produces |
|---|---|---|
| [Planning Agent](../.claude/agents/planning-agent.md) | `Jira Story`, `GitHub Pull Request` | `Map Update`, maps |
| [Coverage Agent](../.claude/agents/coverage-agent.md) | `GitHub CI Failure`, `GCP Log Pattern` | `Coverage Gap` |
| [Incident Agent](../.claude/agents/incident-agent.md) | `GCP Log Pattern`, `Jira Bug` | `Incident RCA`, `Regression Test Request` |
