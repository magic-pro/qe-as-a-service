---
type: Data Type Map
title: Data Type Map — payments-service (Transaction-Scoped)
description: Payment instruction fields handled by payments.ProcessPayment, with boundary scenarios.
scope: transaction
repo: payments-service
generated_by: planning-agent
timestamp: 2026-05-30T19:00:00Z
brd: BRD-PAY-001
jira: STORY-789
tags: [data-type-map, payments, transaction]
---

# Data Type Map — payments-service (Transaction-Scoped)

**Scope:** Payment instruction fields handled by `payments.ProcessPayment`.
**BRD Reference:** BRD-PAY-001
**Jira Story:** STORY-789
**Related:** [Identity Map](identity-map.md)

## Fields

| Field | Type | Constraints | Boundary scenarios to test |
|---|---|---|---|
| amount | decimal.Decimal | > 0, <= 999999999.99, currency-precision | null/zero, min (0.01), max (999999999.99), negative, precision-exceeded (0.001 GBP), rounding boundary (0.005 GBP -> 0.01) |
| currency | string (ISO 4217) | one of GBP,USD,EUR,JPY,BHD | supported, unsupported (ZZZ), empty, JPY 0dp, BHD 3dp |
| cross_border | bool | — | true+missing IBAN, true+present IBAN, false |
| iban | string | required when cross_border | present, empty when cross-border, malformed |

## Decimal precision rules

| Currency | Decimal places | Example valid | Example invalid |
|---|---|---|---|
| GBP/USD/EUR | 2 | 12.34 | 12.345 |
| JPY | 0 | 100 | 100.5 |
| BHD | 3 | 1.234 | 1.2345 |

## Required scenarios (must all be covered)

- amount-boundary (null/zero/min/max/negative)
- amount-precision (per-currency decimal places)
- amount-rounding (half-up / bankers rounding at the boundary)
- currency-unsupported
- cross-border IBAN presence
