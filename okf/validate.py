"""Lint an OKF bundle against the QEaaS profile (okf/conventions.md).

Checks per markdown file:
  - frontmatter present and parses
  - `type` is in the allowed set; required fields for that type are present
  - relative markdown links resolve (bundle-absolute `/x.md` resolves from the root)
  - no `<!-- AGENT: ... -->` placeholders unless `status: template`
  - `derived_from` on findings points at an existing file
Per directory: if an `index.md` exists it must link every sibling doc and every
child directory that holds docs.

Paths matching globs in `<root>/.okfignore` are skipped.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from okf import schema
from okf.frontmatter import FrontmatterError, split

ALWAYS_IGNORE = (".git/*", "*/node_modules/*", "node_modules/*")

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
_INLINE_CODE = re.compile(r"`[^`\n]*`")


@dataclass
class Issue:
    path: str
    code: str
    message: str
    level: str = "error"

    def __str__(self) -> str:
        return f"{self.level.upper():5} {self.path}: [{self.code}] {self.message}"


def _load_ignores(root: Path) -> list[str]:
    patterns = list(ALWAYS_IGNORE)
    f = root / ".okfignore"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def _ignored(rel: str, patterns: list[str]) -> bool:
    for p in patterns:
        if fnmatch.fnmatch(rel, p):
            return True
        # Directory patterns ("dir/") match everything beneath them.
        if p.endswith("/") and (rel + "/").startswith(p):
            return True
    return False


def _links(body: str) -> list[str]:
    stripped = _INLINE_CODE.sub("", _FENCE.sub("", body))
    return _LINK.findall(stripped)


def _resolve(link: str, doc: Path, root: Path) -> Path | None:
    target = link.split("#", 1)[0]
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target):  # anchors, http:, mailto:
        return None
    if target.startswith("/"):
        return (root / target.lstrip("/")).resolve()
    return (doc.parent / target).resolve()


def _valid_timestamp(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False


def validate_doc(path: Path, root: Path) -> list[Issue]:
    rel = str(path.relative_to(root))
    issues: list[Issue] = []
    text = path.read_text(encoding="utf-8")
    try:
        meta, body = split(text)
    except FrontmatterError as exc:
        return [Issue(rel, "frontmatter", str(exc))]
    if meta is None:
        return [Issue(rel, "frontmatter", "missing YAML frontmatter")]

    doc_type = meta.get("type")
    if not doc_type:
        issues.append(Issue(rel, "type", "missing required field `type`"))
        return issues
    if doc_type not in schema.ALLOWED_TYPES:
        issues.append(Issue(rel, "type", f"unknown type {doc_type!r} (see okf/conventions.md)"))

    for field in schema.required_fields(doc_type):
        if meta.get(field) in (None, "", []):
            issues.append(Issue(rel, "required", f"missing `{field}` for type {doc_type!r}"))

    is_template = meta.get("status") == "template"
    if not is_template:
        if "timestamp" in meta and not _valid_timestamp(meta["timestamp"]):
            issues.append(Issue(rel, "timestamp", f"not ISO 8601: {meta['timestamp']!r}"))
        prose = _INLINE_CODE.sub("", _FENCE.sub("", body))
        if schema.PLACEHOLDER in prose or any(schema.PLACEHOLDER in str(v) for v in meta.values()):
            issues.append(Issue(rel, "placeholder", "unfilled <!-- AGENT: --> placeholder in a non-template doc"))

    for link in _links(body):
        target = _resolve(link, path, root)
        if target is not None and not target.exists():
            issues.append(Issue(rel, "link", f"broken link -> {link}"))

    derived = meta.get("derived_from")
    if derived:
        for d in derived if isinstance(derived, list) else [derived]:
            target = _resolve(str(d), path, root)
            if target is not None and not target.exists():
                issues.append(Issue(rel, "derived_from", f"derived_from target not found: {d}"))
    return issues


def validate_index(index: Path, root: Path, docs: set[Path]) -> list[Issue]:
    rel = str(index.relative_to(root))
    try:
        _, body = split(index.read_text(encoding="utf-8"))
    except FrontmatterError:
        return []  # already reported by validate_doc
    linked = {t for t in (_resolve(l, index, root) for l in _links(body)) if t is not None}
    issues = []
    folder = index.parent
    for child in sorted(folder.iterdir()):
        if child == index:
            continue
        if child.is_file() and child.resolve() in docs:
            if child.resolve() not in linked:
                issues.append(Issue(rel, "index", f"does not link sibling {child.name}", "warn"))
        elif child.is_dir() and any(d.is_relative_to(child.resolve()) for d in docs):
            if not any(t == child.resolve() or child.resolve() in t.parents for t in linked):
                issues.append(Issue(rel, "index", f"does not link child dir {child.name}/", "warn"))
    return issues


def validate(root: str | Path) -> list[Issue]:
    root = Path(root).resolve()
    patterns = _load_ignores(root)
    paths = sorted(
        p for p in root.rglob("*.md")
        if not _ignored(str(p.relative_to(root)), patterns)
    )
    docs = {p.resolve() for p in paths}
    issues: list[Issue] = []
    for p in paths:
        issues.extend(validate_doc(p, root))
    for p in paths:
        if p.name == "index.md":
            issues.extend(validate_index(p, root, docs))
    return issues
