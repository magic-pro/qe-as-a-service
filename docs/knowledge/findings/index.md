---
type: Index
title: Findings
description: Agent outputs — Map Update, Coverage Gap, Incident RCA and Regression Test Request docs, each linked to the signal it came from.
tags: [okf, index, findings]
---

# Findings

Every finding is an OKF doc with `derived_from` pointing at a doc in [../signals/](../signals/index.md). `python3 -m okf validate` fails any finding that doesn't cite its signal.

Runtime findings are not committed. The E2E harness writes them under `e2e/runs/`.
