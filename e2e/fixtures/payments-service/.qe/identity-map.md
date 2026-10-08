---
type: Identity Map
title: Identity Map — payments-service (Auth Boundary Slice)
description: Auth boundary scenarios relevant to the payments service layer.
scope: auth-boundary
repo: payments-service
slice_of: "identity-repo:.qe/Domain-Map/identity-map.md"
generated_by: planning-agent
timestamp: 2026-05-30T19:00:00Z
brd: BRD-PAY-001
jira: STORY-789
tags: [identity-map, auth-boundary, payments]
---

# Identity Map — payments-service (Auth Boundary Slice)

**Scope:** Auth boundary relevant to the payments service layer.
**BRD Reference:** BRD-PAY-001
**Jira Story:** STORY-789
**Related:** [Data Type Map](data-type-map.md)

## Token Validation at API Layer

| Scenario | Input | Expected |
|---|---|---|
| Valid JWT, valid scope | Bearer token, correct audience + scope | request processed |
| Expired JWT | token past exp | 401 |
| Missing token | no Authorization header | 401 |
| Wrong scope for POST /payments | token without payments:write | 403 |

## Correlation ID Propagation

| Scenario | Expected |
|---|---|
| X-Correlation-ID present | propagated to downstream + audit log |
| X-Correlation-ID absent | new UUID generated and propagated |

> Note: the service-under-test in this fixture exposes pure validation functions,
> so auth scenarios are documented for traceability; the agent should focus test
> generation on the data-type-map scenarios that map to callable code.
