---
name: build-tests
type: Command
title: /build-tests
description: Invoke the Builder Agent. Takes an approved Story Map and generates test code using the language framework templates. Raises DRAFT PRs for engineer review. Requires status:approved in the Story Map frontmatter.
---

Invoke the Builder Agent as defined in `.claude/agents/builder-agent.md`.

## Usage

```
/build-tests --story-map <path> [--lang <go|pytest|playwright|typescript>] [--repo <repo-name>] [--dry-run]
```

Defaults: `--lang go`, `--repo` derived from Story Map service names.

## Steps

1. Read the Story Map at `--story-map` and confirm `status: approved`
2. Parse the Human Review Required decision table — extract actioned rows only
3. Select test type for each signal (contract / integration / e2e / regression)
4. Read existing framework helpers and test patterns in `frameworks/<lang>/`
5. Read target repo's `.qe/` maps for field definitions and scenarios
6. Generate test files with full traceability comments
7. Write build report to `knowledge/findings/<story-map-key>-build-report.md`
8. Raise DRAFT PR(s) on the target repo

## After Completion

Remind the user:
- Review each generated test file in the DRAFT PR
- Fill in any `UNKNOWN` traceability fields
- Confirm the test captures the intent behind the approved signal
- Remove DRAFT and merge when satisfied
- Run `/coverage-gap` after merging to verify new tests close the identified gaps
