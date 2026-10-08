"""Deterministic tests for OKF normalisation and validation (no LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from okf import expect, schema, validate
from okf.frontmatter import render, split
from okf.normalize import adf_to_markdown, normalize, redact

REPO = Path(__file__).resolve().parents[2]
SIGNALS = REPO / "e2e" / "signals"


def _raw(uc: str) -> dict:
    return json.loads((SIGNALS / uc / "raw.json").read_text())


@pytest.fixture
def jira_doc():
    return normalize("jira", _raw("uc1-jira-story"), base_url="https://synthetic-bank.atlassian.net")


@pytest.fixture
def github_doc():
    log = (SIGNALS / "uc2-github-ci" / "gotest.txt").read_text()
    return normalize("github", _raw("uc2-github-ci"), event="workflow_run", log=log)


@pytest.fixture
def gcp_doc():
    return normalize("gcp", _raw("uc3-gcp-logs"))


# ---------------------------------------------------------------- normalise


def test_jira_story_signal(jira_doc):
    m = jira_doc.meta
    assert m["type"] == "Jira Story"
    assert m["key"] == "PAY-214"
    assert m["brd"] == "BRD-PAY-001"
    assert m["resource"] == "https://synthetic-bank.atlassian.net/browse/PAY-214"
    assert m["timestamp"] == "2026-09-26T14:05:00Z"
    assert jira_doc.relpath == "jira/PAY-214.md"
    # ADF acceptance criteria survive as an ordered list.
    assert "### Acceptance Criteria" in jira_doc.body
    assert "2. AC2:" in jira_doc.body
    assert "`STORY-789`" in jira_doc.body


def test_github_ci_failure_signal(github_doc):
    m = github_doc.meta
    assert m["type"] == "GitHub CI Failure"
    assert m["key"] == "synthetic-bank/payments-service#run-9812345670"
    assert m["pull_requests"] == [57]
    assert "ROUND_HALF_EVEN" in m["description"]
    assert "--- FAIL: TestAmountRounding_HalfUp" in github_doc.body
    # Passing subtests are not part of the excerpt.
    assert "--- PASS" not in github_doc.body


def test_gcp_log_pattern_signal(gcp_doc):
    m = gcp_doc.meta
    assert m["type"] == "GCP Log Pattern"
    assert m["severity"] == "CRITICAL"
    assert m["services"] == ["auth-gateway", "payments-service"]
    assert "| ERROR | auth-gateway | `totp_replay_accepted` | 3 |" in gcp_doc.body
    assert "totp.replay_cache.enabled=false" in gcp_doc.body


@pytest.mark.parametrize("fixture", ["jira_doc", "github_doc", "gcp_doc"])
def test_signals_are_pii_masked(fixture, request):
    text = request.getfixturevalue(fixture).text()
    for leaked in ("@example.com", "203.0.113.24", "KW81CBKU", "12345678"):
        assert leaked not in text


@pytest.mark.parametrize("fixture", ["jira_doc", "github_doc", "gcp_doc"])
def test_signals_pass_validation(fixture, request, tmp_path):
    request.getfixturevalue(fixture).write(tmp_path)
    assert validate.validate(tmp_path) == []


def test_redact_patterns():
    assert redact("mail a.b+c@bank.co.uk now.") == "mail <email> now."
    assert redact("iban GB82WEST12345698765432") == "iban <iban>"
    assert redact("card 4111 1111 1111 1111") == "card <pan>"
    assert redact("call +44 7700 900123") == "call <phone>"
    # Amounts and timestamps are not PII.
    assert redact("amount 999999999.99 at 2026-09-27T03:10:04Z") == "amount 999999999.99 at 2026-09-27T03:10:04Z"


def test_adf_nested_lists():
    adf = {"type": "doc", "content": [{"type": "bulletList", "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "one"}]}]},
    ]}]}
    assert adf_to_markdown(adf).strip() == "- one"


def test_frontmatter_round_trip():
    meta = {"type": "Index", "title": "t", "description": "d"}
    got_meta, body = split(render(meta, "# Body\n"))
    assert got_meta == meta and body.strip() == "# Body"


# ---------------------------------------------------------------- validate


def _write(root: Path, rel: str, meta: dict | None, body: str = "# x\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(meta, body) if meta is not None else body)
    return p


def _codes(root: Path) -> set[str]:
    return {i.code for i in validate.validate(root) if i.level == "error"}


BASE = {"title": "t", "description": "d", "timestamp": "2026-09-27T00:00:00Z"}


def test_validate_missing_frontmatter(tmp_path):
    _write(tmp_path, "a.md", None)
    assert _codes(tmp_path) == {"frontmatter"}


def test_validate_missing_and_unknown_type(tmp_path):
    _write(tmp_path, "a.md", {"title": "t", "description": "d"})
    _write(tmp_path, "b.md", {"type": "Spreadsheet", **BASE})
    assert _codes(tmp_path) == {"type"}


def test_validate_broken_link(tmp_path):
    _write(tmp_path, "a.md", {"type": "Architecture", **BASE}, "see [b](b.md) and [c](missing.md)")
    _write(tmp_path, "b.md", {"type": "Architecture", **BASE})
    issues = [i for i in validate.validate(tmp_path) if i.code == "link"]
    assert len(issues) == 1 and "missing.md" in issues[0].message


def test_validate_links_in_code_are_ignored(tmp_path):
    _write(tmp_path, "a.md", {"type": "Architecture", **BASE}, "`[x](nope.md)`\n```\n[y](nope.md)\n```\n")
    assert _codes(tmp_path) == set()


def test_validate_placeholder_only_in_non_templates(tmp_path):
    body = "BRD: <!-- AGENT: insert -->"
    _write(tmp_path, "tpl.md", {"type": "Data Type Map", "status": "template", **BASE}, body)
    _write(tmp_path, "real.md", {"type": "Data Type Map", **BASE}, body)
    issues = [i for i in validate.validate(tmp_path) if i.code == "placeholder"]
    assert [i.path for i in issues] == ["real.md"]


def test_validate_finding_requires_derived_from(tmp_path):
    _write(tmp_path, "f.md", {"type": "Coverage Gap", **BASE})
    _write(tmp_path, "g.md", {"type": "Coverage Gap", "derived_from": "signals/nope.md", **BASE})
    codes = [(i.path, i.code) for i in validate.validate(tmp_path)]
    assert ("f.md", "required") in codes
    assert ("g.md", "derived_from") in codes


def test_validate_agent_needs_no_timestamp(tmp_path):
    _write(tmp_path, "agent.md", {"type": "Agent", "title": "t", "description": "d", "name": "x"})
    assert _codes(tmp_path) == set()


def test_validate_index_must_link_children(tmp_path):
    _write(tmp_path, "index.md", {"type": "Index", "title": "t", "description": "d"}, "- [a](a.md)\n")
    _write(tmp_path, "a.md", {"type": "Architecture", **BASE})
    _write(tmp_path, "b.md", {"type": "Architecture", **BASE})
    warns = [i.message for i in validate.validate(tmp_path) if i.code == "index"]
    assert warns == ["does not link sibling b.md"]


def test_okfignore(tmp_path):
    (tmp_path / ".okfignore").write_text("README.md\nruns/\n")
    _write(tmp_path, "README.md", None)
    _write(tmp_path, "runs/report.md", None)
    assert validate.validate(tmp_path) == []


def test_schema_signal_requires_source_key_resource():
    assert {"source", "key", "resource"} <= set(schema.required_fields("Jira Story"))


# ---------------------------------------------------------------- expect


def test_expect_checks_type_derived_from_and_keywords(tmp_path):
    _write(tmp_path, "knowledge/signals/jira/PAY-214.md", {"type": "Jira Story", **BASE})
    _write(
        tmp_path,
        "knowledge/findings/uc1.md",
        {"type": "Map Update", "derived_from": "../signals/jira/PAY-214.md", **BASE},
        "Added KWD and OMR at 3dp",
    )
    spec = tmp_path / "expected.yaml"
    spec.write_text(
        "outputs:\n"
        "  - path: knowledge/findings/uc1.md\n"
        "    type: Map Update\n"
        "    derived_from: signals/jira/PAY-214.md\n"
        "    keywords: [KWD, OMR, JPY]\n"
    )
    results = {label: ok for label, ok, _ in expect.check(spec, tmp_path)}
    assert results["knowledge/findings/uc1.md type == Map Update"]
    assert results["knowledge/findings/uc1.md derived_from -> signals/jira/PAY-214.md"]
    assert results["knowledge/findings/uc1.md mentions 'KWD'"]
    assert not results["knowledge/findings/uc1.md mentions 'JPY'"]
