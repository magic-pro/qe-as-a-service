---
type: Index
title: Artifacts
description: Cross-cutting Planning Agent outputs that stay in qe-as-a-service.
tags: [okf, index, artifacts]
---

# Artifacts

- [Test Strategy template](test-strategy-template.md): `/plan-analysis` renders this to `artifacts/test-strategy.md`
- [Infrastructure Complexity Map template](infra-map-template.md): rendered to `artifacts/infra-map.md`

Rendered artifacts drop `status: template`, fill every `<!-- AGENT: -->` field, and set `derived_from` to the signal docs they were built from.
