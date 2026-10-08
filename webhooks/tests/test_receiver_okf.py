"""Receiver → OKF signal doc → agent routing, using the synthetic E2E signals.

Run from repo root:  python -m pytest webhooks/tests
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

import pytest

SECRET = "test-secret"
for var in ("GITHUB_WEBHOOK_SECRET", "JIRA_WEBHOOK_SECRET", "CONFLUENCE_WEBHOOK_SECRET"):
    os.environ.setdefault(var, SECRET)
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("PUBSUB_PUSH_AUDIENCE", "https://example.test/webhooks/gcp-monitoring")

from webhooks import receiver  # noqa: E402  (env must be set first)
from okf.frontmatter import split  # noqa: E402

SIGNALS = Path(__file__).resolve().parents[2] / "e2e" / "signals"


@pytest.fixture
def client(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(receiver, "invoke_agent", lambda agent, prompt: calls.append((agent, prompt)))
    monkeypatch.setattr(receiver, "SIGNALS_DIR", tmp_path)
    monkeypatch.setattr(receiver, "verify_pubsub_token", lambda _h: True)
    c = receiver.app.test_client()
    c.calls = calls
    c.signals_dir = tmp_path
    return c


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _doc_from_prompt(prompt: str) -> Path:
    first = prompt.splitlines()[0]
    assert first.startswith("Signal doc: "), prompt
    return Path(first[len("Signal doc: "):])


def test_uc1_jira_story_routes_to_planning_with_signal_doc(client):
    body = (SIGNALS / "uc1-jira-story" / "raw.json").read_bytes()
    r = client.post("/webhooks/jira", data=body, headers={"X-Hub-Signature": _sign(body)})
    assert r.status_code == 202
    [(agent, prompt)] = client.calls
    assert agent == "planning-agent"
    doc = _doc_from_prompt(prompt)
    assert doc == client.signals_dir / "jira" / "PAY-214.md"
    meta, _ = split(doc.read_text())
    assert meta["type"] == "Jira Story" and meta["key"] == "PAY-214"


def test_uc2_github_ci_failure_routes_to_coverage_with_signal_doc(client):
    body = (SIGNALS / "uc2-github-ci" / "raw.json").read_bytes()
    r = client.post(
        "/webhooks/github",
        data=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "workflow_run"},
    )
    assert r.status_code == 202
    [(agent, prompt)] = client.calls
    assert agent == "coverage-agent"
    meta, _ = split(_doc_from_prompt(prompt).read_text())
    assert meta["type"] == "GitHub CI Failure"
    assert meta["pull_requests"] == [57]


def test_uc3_gcp_alert_routes_to_incident_with_signal_doc(client):
    data = (SIGNALS / "uc3-gcp-logs" / "raw.json").read_bytes()
    envelope = {"message": {"data": base64.b64encode(data).decode()}}
    r = client.post("/webhooks/gcp-monitoring", json=envelope, headers={"Authorization": "Bearer x"})
    assert r.status_code == 202
    [(agent, prompt)] = client.calls
    assert agent == "incident-agent"
    text = _doc_from_prompt(prompt).read_text()
    meta, _ = split(text)
    assert meta["type"] == "GCP Log Pattern" and meta["severity"] == "CRITICAL"
    assert "@example.com" not in text


def test_bad_signature_is_rejected_and_nothing_recorded(client):
    body = (SIGNALS / "uc1-jira-story" / "raw.json").read_bytes()
    r = client.post("/webhooks/jira", data=body, headers={"X-Hub-Signature": "sha256=bad"})
    assert r.status_code == 401
    assert client.calls == []
    assert not any(client.signals_dir.rglob("*.md"))


def test_normalisation_failure_still_routes_agent(client, monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("bad payload")

    monkeypatch.setattr(receiver, "normalize", boom)
    body = json.dumps(json.loads((SIGNALS / "uc2-github-ci" / "raw.json").read_text())).encode()
    client.post("/webhooks/github", data=body, headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "workflow_run"})
    [(agent, prompt)] = client.calls
    assert agent == "coverage-agent" and not prompt.startswith("Signal doc:")
