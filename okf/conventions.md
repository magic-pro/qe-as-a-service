---
type: Conventions
title: QEaaS OKF conventions
description: The QEaaS profile of the Open Knowledge Format v0.1 — doc types, required fields and linking rules shared by every agent.
tags: [okf, conventions]
timestamp: 2026-09-27T00:00:00Z
---

# QEaaS OKF conventions

QEaaS stores all of its knowledge as [OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog) documents. An OKF document is a markdown file whose YAML frontmatter describes it. Every signal, map, finding and agent in the pipeline uses the same format, so each agent reads and writes one shape.

The machine-readable version of these rules is `okf/schema.py`, and `python3 -m okf validate <dir>` enforces them.

## Frontmatter

| Field | Required | Notes |
|---|---|---|
| `type` | always | One of the types listed below |
| `title` | always | Human-readable name |
| `description` | always | One sentence |
| `timestamp` | not for `Agent`, `Command`, `Index`, `Log` | ISO 8601 UTC |
| `tags` | optional | List |
| `resource` | signals | URL of the origin (Jira issue, GitHub run, GCP incident) |
| `source`, `key` | signals | `jira` / `github` / `gcp`, plus a stable ID (`PAY-214`, `org/repo#run-123`) |
| `derived_from` | findings | Bundle path(s) of the signal doc(s) the finding was produced from |
| `brd`, `jira` | maps | Traceability to the requirement and the story |
| `scope`, `repo` | maps | Slice scope (`identity`, `transaction`, `auth-boundary`) and the target repo |
| `generated_by` | produced docs | Agent name |
| `status` | optional | `template` exempts a doc from the placeholder check |
| `slice_of` / `slices` | maps | Cross-repo references written as `<repo>:<path>`, not links, because target repos live apart |

Frontmatter in maps must not contain `|` or the word `float`, because the eval scripts grep map files.

## Types

| Family | Types | Written by |
|---|---|---|
| Signals | `Jira Story`, `Jira Bug`, `Jira Epic`, `GitHub CI Failure`, `GitHub Pull Request`, `GCP Log Pattern` | `okf/normalize.py` (from `webhooks/receiver.py`) |
| Maps | `Data Type Map`, `Identity Map`, `Domain Map`, `Test Strategy`, `Infra Map` | Planning Agent |
| Findings | `Map Update`, `Coverage Gap`, `Incident RCA`, `Regression Test Request` | Planning, Coverage and Incident agents |
| Tooling | `Agent`, `Command` | Humans (`.claude/`) |
| Docs | `Index`, `Log`, `Architecture`, `Conventions`, `Design Spec`, `Implementation Plan` | Humans |

## Bundle layout

```
knowledge/
├── index.md
├── signals/{jira,github,gcp}/   one doc per inbound signal
└── findings/                    agent outputs, each with derived_from → a signal
<repo>/.qe/                      per-repo OKF bundle: maps + index.md + log.md
```

## Rules

1. **Links.** Use normal relative markdown links inside a bundle. `/path.md` resolves from the bundle root.
2. **Indexes.** Each bundle folder has an `index.md` that links every doc and sub-folder in it.
3. **Change history.** Every change an agent makes to a bundle adds one line to that bundle's `log.md`, in the form `- <timestamp> · <agent> · <what changed> · derived_from <signal>`.
4. **Findings cite their signal.** A finding without `derived_from` fails validation.
5. **PII.** Signals are masked on the way in: emails, IBANs, card numbers, phone numbers, IPs, and the fields listed in `target-repos/*.json`.
