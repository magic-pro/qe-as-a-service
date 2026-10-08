"""Read and write OKF documents: YAML frontmatter + markdown body."""

from __future__ import annotations

from typing import Any

import yaml

DELIM = "---"


class FrontmatterError(ValueError):
    pass


def split(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return (frontmatter, body). frontmatter is None when the doc has none."""
    if not text.startswith(DELIM + "\n"):
        return None, text
    end = text.find("\n" + DELIM + "\n", len(DELIM))
    if end == -1:
        # Frontmatter running to EOF with no body.
        if text.rstrip().endswith("\n" + DELIM):
            end = text.rstrip().rfind("\n" + DELIM)
        else:
            raise FrontmatterError("unterminated frontmatter block")
    raw = text[len(DELIM) + 1 : end]
    body = text[end + len(DELIM) + 2 :]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return meta, body


def render(meta: dict[str, Any], body: str) -> str:
    head = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000).rstrip()
    return f"{DELIM}\n{head}\n{DELIM}\n\n{body.lstrip()}"
