---
name: incident-rca
description: Invoke the Incident Analysis Agent. Provide an alert URL, GCP incident ID, Jira ticket, or paste log output. The agent performs root cause analysis, presents findings for human confirmation, then generates reproduction steps, a regression test request, and an incident ticket.
---

Invoke the Incident Analysis Agent as defined in `.claude/agents/incident-agent.md`.

## Usage

```
/incident-rca [--alert <GCP alert URL>] [--jira <ticket ID>] [--github-issue <issue number>] [--since <ISO datetime>]
```

Or paste raw log output / error description directly after the command.

## Steps

1. Gather all available signals (alert, logs, traces, recent PRs)
2. Build timeline and classify failure
3. Assess finance impact (monetary, regulatory, audit, identity, PII)
4. **STOP — present RCA to human for confirmation**
5. On confirmation: generate reproduction steps, incident ticket, regression test request

## Important

Do not proceed past Step 4 without explicit human confirmation ("Yes" or corrected findings).

Do not include real PII from production logs in any output — replace with synthetic equivalents.

After completion, the regression test request should be taken to the affected target repo and executed with `/create-tests`.
