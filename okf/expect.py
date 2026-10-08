"""Assert an agent's OKF output against a use case's expected.yaml.

expected.yaml shape:
    outputs:
      - path: knowledge/findings/uc1-map-update.md   # relative to workspace
        type: Map Update
        derived_from: knowledge/signals/jira/PAY-214.md
        keywords: [BHD, "3"]          # case-insensitive, all must appear
      - path: .qe/data-type-map.md
        type: Data Type Map
        keywords: [BHD]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from okf.frontmatter import FrontmatterError, split


def check(expected_file: str | Path, workspace: str | Path) -> list[tuple[str, bool, str]]:
    ws = Path(workspace)
    spec: dict[str, Any] = yaml.safe_load(Path(expected_file).read_text())
    results: list[tuple[str, bool, str]] = []
    for out in spec.get("outputs", []):
        path = ws / out["path"]
        label = out["path"]
        if not path.exists():
            results.append((f"{label} exists", False, "missing"))
            continue
        results.append((f"{label} exists", True, ""))
        try:
            meta, body = split(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            results.append((f"{label} frontmatter", False, str(exc)))
            continue
        meta = meta or {}
        if "type" in out:
            ok = meta.get("type") == out["type"]
            results.append((f"{label} type == {out['type']}", ok, f"got {meta.get('type')!r}"))
        if "derived_from" in out:
            got = meta.get("derived_from")
            got_list = [str(g) for g in (got if isinstance(got, list) else [got] if got else [])]
            want = out["derived_from"]
            ok = any(g.endswith(want) or want.endswith(g.lstrip("./")) for g in got_list)
            results.append((f"{label} derived_from -> {want}", ok, f"got {got!r}"))
        text = (body or "").lower() + " " + str(meta).lower()
        for kw in out.get("keywords", []):
            ok = str(kw).lower() in text
            results.append((f"{label} mentions '{kw}'", ok, ""))
    return results
