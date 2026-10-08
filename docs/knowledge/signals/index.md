---
type: Index
title: Signals
description: Normalised inbound signals — one OKF doc per Jira, GitHub or GCP Log Explorer event, PII-masked.
tags: [okf, index, signals]
---

# Signals

`webhooks/receiver.py` writes these using `okf/normalize.py`. You can also create one by hand with `python3 -m okf normalize`.

- [jira/](jira/): `Jira Story`, `Jira Bug` and `Jira Epic` docs, named `<KEY>.md`
- [github/](github/): `GitHub CI Failure` and `GitHub Pull Request` docs
- [gcp/](gcp/): `GCP Log Pattern` docs, one per alert incident or log pattern

Runtime signal docs are not committed. Each folder holds a `.gitkeep` so the links resolve.
