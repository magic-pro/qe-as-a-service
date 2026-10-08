---
type: Identity Map
title: Identity Map — Microservices Repo (Auth Boundary Slice)
description: Auth boundary only — token validation at API layer, RBAC at service level, service-to-service auth.
status: template
scope: auth-boundary
repo: microservices-repo
slice_of: "identity-repo:.qe/Domain-Map/identity-map.md"
generated_by: planning-agent
timestamp: "<!-- AGENT: insert ISO 8601 UTC -->"
brd: "<!-- AGENT: insert -->"
jira: "<!-- AGENT: insert -->"
derived_from: []
tags: [identity-map, auth-boundary]
---

# Identity Map — Microservices Repo (Auth Boundary Slice)

> Full identity map (KYC/AML/fraud/ForgeRock/Daon): `identity-repo:.qe/Domain-Map/identity-map.md` (see `slice_of` in the frontmatter)
> This slice covers only what microservice developers need to write tests without leaving this repo.

---

## Token Validation at API Layer

| Scenario | Input | Expected | Priority |
|---|---|---|---|
| Valid JWT, valid scope | Bearer token, correct audience + scope | 200, request processed | Critical |
| Expired JWT | Bearer token past `exp` | 401 | Critical |
| Invalid signature | Tampered JWT | 401 | Critical |
| Wrong audience | JWT with `aud` for different service | 401 | High |
| Missing token | No Authorization header | 401 | High |
| Malformed token | Not valid JWT structure | 400 | High |
| Revoked token | Token in revocation list (check via ForgeRock) | 401 | High |
| <!-- AGENT: add --> | | | |

## RBAC at Service Layer

| Role | Permitted Endpoints | Denied Endpoints | Test |
|---|---|---|---|
| Customer | `GET /accounts/{own_id}`, `POST /payments` | `GET /accounts/{other_id}`, `GET /admin/*` | Cross-account read |
| Service Account (internal) | Service-specific scopes | Out-of-scope endpoints | Scope boundary test |
| Admin | All | N/A | Horizontal escalation check |
| <!-- AGENT: add roles relevant to this service --> | | | |

## Service-to-Service Auth

| Scenario | Flow | Expected | Priority |
|---|---|---|---|
| Valid client credentials | Service A calls Service B with valid token | 200 | High |
| Missing service token | Service A calls Service B without token | 401 | High |
| Wrong scope | Service A calls endpoint outside its scope | 403 | High |
| Expired service token | Service A uses expired client creds token | 401, must refresh | High |

## Correlation ID Propagation

Every service must propagate `X-Correlation-ID` and `X-Request-ID` headers across all service calls. Test scenarios:

| Scenario | Expected |
|---|---|
| Correlation ID present in inbound request | Propagated to all downstream calls |
| Correlation ID absent | New UUID generated and propagated |
| Correlation ID in audit log | Matches inbound value |
