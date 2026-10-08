---
type: Architecture
title: QEaaS Architecture
description: How signals flow through the QEaaS strategic agents into shift-left target repos, and the v1–v3 roadmap.
timestamp: 2026-09-27T00:00:00Z
tags: [architecture, okf]
---

# QEaaS Architecture

## How It Works

```mermaid
flowchart TD
    Signals["GitHub · Jira · Confluence · GCP · OTEL"]
    OKF["OKF signal docs<br/>knowledge/signals/"]

    subgraph QEaaS["qe-as-a-service"]
        PA[Planning Agent] --> CA[Coverage Agent]
        PA --> IA[Incident Agent]
    end

    subgraph Repos["Target Repos · Shift Left"]
        TC[Test Creator] --> CI[CI Tests]
        CI -->|failure| TH[Test Healer]
    end

    Staging["Staging · Real Systems"]

    Signals -->|"normalize + PII mask"| OKF
    OKF --> QEaaS
    QEaaS -->|"findings (derived_from → signal)"| OKF
    QEaaS -->|".qe/ OKF maps via PR"| Repos
    Repos --> Staging
    Staging -->|"gaps"| CA
```

Every arrow carries an OKF doc: markdown with typed frontmatter. Conventions are in [../okf/conventions.md](../okf/conventions.md), and the bundle entry point is [../knowledge/index.md](../knowledge/index.md).

---

## Versions

```mermaid
timeline
    v1 : Plan · Create · Heal
       : Manual commands
    v2 : + Coverage · Incident
       : + Auto-heal on CI failure
    v3 : + Webhooks on Cloud Run
       : Fully automated
```
