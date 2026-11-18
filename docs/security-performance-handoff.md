---
type: Design Spec
title: Security and performance QE handoff
description: Approval and reporting contract for the two local QE specialists
timestamp: 2026-11-18T00:00:00Z
---

# Security and performance QE handoff

1. **Planning** records the required control or performance budget in the Test Strategy and links the relevant infrastructure or identity map. Scope the work to a synthetic fixture or a local test target.
2. **QE Analysis** maps the evidence to a Story Map signal. In the decision table, put `track: security` or `track: performance` in **Notes** along with the Planning artifact, target checkout, fixture and expected result. The engineer marks the selected rows `Build new test` or `Update assertion` and the Story Map `status: approved`. Approval covers only the specified work. The general Builder skips rows assigned to these tracks.
3. **Build and execute** by selecting **Security Builder & Executor** or **Performance Builder & Executor** in a local Copilot session and supplying the approved Story Map path. They use your Copilot-selected model. They may write local tests and run approved checks, but they do not start remote runs, push branches, raise PRs or bypass local permissions. Stop if the target checkout, approval, fixture, or required limits are missing.

| Track | Example Planning input |
|---|---|
| Security | A synthetic support operator may view invoices for its assigned tenant only. Verify allow and deny decisions in the local policy module. |
| Performance | A representative synthetic batch of 100 invoice records must meet the approved local p95 budget. Planning specifies warm-up, sample count, concurrency, time limit and the reference environment. |

Write an OKF `Build Report` to `knowledge/findings/<signal-key>-<track>-build-report.md`. Include `title`, `description`, UTC `timestamp`, `generated_by` (the specialist's agent ID), and `derived_from` linking to the approved Story Map. In the body, list the approved signal, generated test paths, exact command run, environment/fixture, pass/fail/blocked outcome and any remaining gaps. Don't write raw secrets, customer data or unredacted logs. Validate the report against `okf/conventions.md`.

The Agent Twin shows both agents in its roster. In a Copilot session with opted-in hooks, session and subagent activity appears in the Copilot section; the overview does not infer a QE agent's active status from a report.
