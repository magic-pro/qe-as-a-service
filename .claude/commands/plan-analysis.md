---
name: plan-analysis
description: Invoke the Planning & Analysis Agent. Provide BRD text, Jira story ID/URL, and/or architecture diagram. The agent analyses inputs, writes cross-cutting artifacts to artifacts/, slices maps by repo, and raises PRs on target repos to place .qe/ maps and .claude/agents/ templates in place.
---

Invoke the Planning & Analysis Agent as defined in `.claude/agents/planning-agent.md`.

The user may provide any combination of:
- BRD text (pasted directly or Confluence page URL/ID)
- Jira story ID or URL
- Architecture diagram description or Confluence page
- GitHub repo URL for a new service or dependency change

If MCP tools are connected, use them to fetch source documents. If not, work with pasted input.

## Steps

1. Confirm what inputs you have received
2. Run all five analysis steps from the agent prompt
3. Write cross-cutting artifacts:
   - `artifacts/test-strategy.md`
   - `artifacts/infra-map.md`
4. Produce sliced maps:
   - Identity repo slice → `.qe/data-type-map.md` (identity-scoped), `.qe/identity-map.md` (full)
   - Microservices repo slice → `.qe/data-type-map.md` (transaction-scoped), `.qe/identity-map.md` (auth boundary)
5. Raise PRs on target repos (via GitHub MCP if connected):
   - Copy agent templates from `repo-templates/` if `.claude/agents/` not already present in target repo
   - Drop sliced `.qe/` maps into each repo
   - PR title: `[QEaaS] Add QE maps for <story-id>`
6. If GitHub MCP not connected, output all files clearly labelled for manual PR creation

After completion, remind the user:
- Review the PRs on each target repo
- Merge when satisfied — this unlocks `/create-tests` inside those repos
