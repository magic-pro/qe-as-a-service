---
name: qe-analysis
type: Command
title: /qe-analysis
description: Invoke the QE Analysis Agent. Aggregates daily signals from api.proto merges, incident findings, Jira stories, and Confluence BRDs into a correlated Story Map. Produces a pending-review Story Map that a human must approve before the Builder Agent can act.
---

Invoke the QE Analysis Agent as defined in `.claude/agents/qe-analysis-agent.md`.

## Usage

```
/qe-analysis [--since <hours>] [--proto-repo <owner/repo>]
```

Defaults: `--since 24` (last 24 hours), `--proto-repo` from `target-repos/` config.

## Steps

1. Confirm the look-back window and proto repo with the user
2. Scan api.proto repo merges via GitHub MCP
3. Read incident findings from `knowledge/findings/`
4. Fetch Jira stories via Atlassian MCP
5. Fetch Confluence pages via Atlassian MCP
6. Correlate signals and build Story Map sections
7. Write `knowledge/findings/<YYYY-MM-DD>-story-map.md` with `status: pending-review`

## After Completion

Remind the user:
- Open `knowledge/findings/<date>-story-map.md`
- Review each service section and complete the **Human Review Required** decision table
- Mark rows as: `Build new test`, `Update assertion`, or `Skip — reason: ___`
- Change `status: pending-review` → `status: approved` in the frontmatter
- Then run `/build-tests --story-map knowledge/findings/<file>` to invoke the Builder Agent
