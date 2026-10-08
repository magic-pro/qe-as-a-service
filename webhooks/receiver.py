"""
QEaaS Webhook Receiver (v3)

Deployed on Cloud Run. Receives webhooks from GitHub, Jira, Confluence, and GCP
Cloud Monitoring. Each GitHub / Jira / GCP event is first normalised into an OKF
signal doc (okf/normalize.py → knowledge/signals/<source>/), then routed to the
appropriate QEaaS agent with the doc path as its input.

Deploy: see deploy/cloud-run/
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response, abort, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from okf.normalize import normalize

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# All secrets are required — fail-closed at startup if missing.
GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
JIRA_WEBHOOK_SECRET = os.environ["JIRA_WEBHOOK_SECRET"]
CONFLUENCE_WEBHOOK_SECRET = os.environ["CONFLUENCE_WEBHOOK_SECRET"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
# The full Cloud Run URL configured as the audience on the Pub/Sub push subscription,
# e.g. https://qe-as-a-service-webhook-xyz.a.run.app/webhooks/gcp-monitoring
PUBSUB_PUSH_AUDIENCE = os.environ["PUBSUB_PUSH_AUDIENCE"]
# Where OKF signal docs are written; agents run with the same working dir.
SIGNALS_DIR = Path(os.environ.get("OKF_SIGNALS_DIR", "knowledge/signals"))
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")

_GOOGLE_REQUEST = google_requests.Request()
_GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


def _verify_hmac_sha256(secret: str, payload: bytes, signature_header: str) -> bool:
    """Constant-time verify `X-Hub-Signature(-256)` style headers (`sha256=<hex>`)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_github_signature(payload: bytes, signature: str) -> bool:
    return _verify_hmac_sha256(GITHUB_WEBHOOK_SECRET, payload, signature)


def verify_jira_signature(payload: bytes, signature: str) -> bool:
    return _verify_hmac_sha256(JIRA_WEBHOOK_SECRET, payload, signature)


def verify_confluence_signature(payload: bytes, signature: str) -> bool:
    return _verify_hmac_sha256(CONFLUENCE_WEBHOOK_SECRET, payload, signature)


def verify_pubsub_token(auth_header: str) -> bool:
    """Validate the Google-signed OIDC token attached to authenticated Pub/Sub pushes.

    The Pub/Sub push subscription must be configured with `--push-auth-service-account`
    and `--push-auth-token-audience=<PUBSUB_PUSH_AUDIENCE>`. Google then attaches a
    short-lived ID token in the `Authorization: Bearer …` header.
    """
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[len("Bearer "):]
    try:
        claims = id_token.verify_oauth2_token(
            token, _GOOGLE_REQUEST, audience=PUBSUB_PUSH_AUDIENCE
        )
    except ValueError as exc:
        logger.warning("Pub/Sub OIDC token verification failed: %s", exc)
        return False
    return claims.get("iss") in _GOOGLE_ISSUERS


def invoke_agent(agent: str, prompt: str) -> None:
    """Fire-and-forget agent invocation via Claude Code CLI.

    Uses `claude -p` (print/non-interactive mode) and instructs the orchestrator
    to dispatch to the named subagent defined in .claude/agents/<agent>.md.

    Reliability note: this relies on the deployment running with CPU always
    allocated (see service.yaml `run.googleapis.com/cpu-throttling: "false"`)
    so the spawned subprocess keeps running after the HTTP request returns.
    For production-grade durability, replace this with a Cloud Tasks enqueue
    that dispatches to a Cloud Run Job, where each agent run is its own
    tracked execution with retries and visibility.
    """
    full_prompt = f"Use the {agent} subagent for this task.\n\n{prompt}"
    subprocess.Popen(
        ["claude", "-p", full_prompt],
        env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Invoked agent: %s", agent)


def record_signal(source: str, payload: dict[str, Any], **kwargs: Any) -> Optional[Path]:
    """Normalise a raw event into a PII-masked OKF signal doc and write it.

    Never blocks routing: on failure the agent still runs with the task prompt alone.
    """
    try:
        path = normalize(source, payload, **kwargs).write(SIGNALS_DIR)
    except Exception:  # noqa: BLE001 — a malformed payload must not drop the webhook
        logger.exception("OKF normalisation failed for %s event", source)
        return None
    logger.info("Recorded OKF signal: %s", path)
    return path


def with_signal(doc: Optional[Path], task: str) -> str:
    """Agent prompt: the signal doc is the input contract; the task says what to do."""
    return f"Signal doc: {doc}\n\n{task}" if doc else task


@app.route("/webhooks/github", methods=["POST"])
def github_webhook() -> Response:
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(request.data, signature):
        abort(401, "Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload: dict[str, Any] = request.get_json(force=True)

    if event == "pull_request" and payload.get("action") in ("opened", "synchronize"):
        pr = payload["pull_request"]
        # New PR — check if it contains new service, new dependency bump
        if _is_new_service_pr(pr) or _is_dependency_bump(pr):
            doc = record_signal("github", payload, event=event)
            invoke_agent(
                "planning-agent",
                with_signal(
                    doc,
                    f"New PR detected: {pr['html_url']}. "
                    f"Check if this introduces a new service or dependency bump. "
                    f"If so, re-assess infrastructure complexity map and flag any "
                    f"test strategy gaps.",
                ),
            )

    elif event == "workflow_run" and payload.get("action") == "completed":
        run = payload["workflow_run"]
        if run["conclusion"] == "failure":
            doc = record_signal("github", payload, event=event)
            invoke_agent(
                "coverage-agent",
                with_signal(
                    doc,
                    f"CI failure detected: {run['html_url']}. "
                    f"Scan for any new code paths that may have been introduced "
                    f"and identify coverage gaps.",
                ),
            )

    elif event == "push" and _is_new_service_push(payload):
        invoke_agent(
            "planning-agent",
            f"New service or repository detected: {payload['repository']['full_name']}. "
            f"Analyse the repository structure and raise a planning request.",
        )

    return jsonify({"status": "accepted"}), 202


@app.route("/webhooks/jira", methods=["POST"])
def jira_webhook() -> Response:
    signature = request.headers.get("X-Hub-Signature", "")
    if not verify_jira_signature(request.data, signature):
        abort(401, "Invalid signature")

    payload: dict[str, Any] = request.get_json(force=True)
    event_type = payload.get("webhookEvent", "")

    if event_type in ("jira:issue_created", "jira:issue_updated"):
        issue = payload.get("issue", {})
        issue_type = issue.get("fields", {}).get("issuetype", {}).get("name", "")
        status = issue.get("fields", {}).get("status", {}).get("name", "")
        # Every issue event is recorded, whether or not it triggers an agent.
        doc = record_signal("jira", payload, base_url=JIRA_BASE_URL)

        if issue_type in ("Epic", "Story") and "acceptance" in str(
            issue.get("fields", {}).get("description", "")
        ).lower():
            invoke_agent(
                "planning-agent",
                with_signal(
                    doc,
                    f"Jira story updated with acceptance criteria: {issue['key']}. "
                    f"Re-assess test strategy and update maps if needed.",
                ),
            )

        elif status == "In Development" and issue_type == "Story":
            invoke_agent(
                "planning-agent",
                with_signal(
                    doc,
                    f"Jira story moved to In Development: {issue['key']}. "
                    f"Ensure test strategy and .qe/ maps are up to date for this story.",
                ),
            )

        elif issue_type == "Bug" and issue.get("fields", {}).get("priority", {}).get("name") in ("Critical", "High"):
            invoke_agent(
                "incident-agent",
                with_signal(
                    doc,
                    f"High-priority bug raised in Jira: {issue['key']}. "
                    f"Analyse available logs and traces for this issue and prepare RCA.",
                ),
            )

    return jsonify({"status": "accepted"}), 202


@app.route("/webhooks/confluence", methods=["POST"])
def confluence_webhook() -> Response:
    signature = request.headers.get("X-Hub-Signature", "")
    if not verify_confluence_signature(request.data, signature):
        abort(401, "Invalid signature")

    payload: dict[str, Any] = request.get_json(force=True)
    event_type = payload.get("event", "")

    if event_type in ("page_created", "page_updated"):
        page = payload.get("page", {})
        title = page.get("title", "").lower()
        space = page.get("space", {}).get("key", "")

        if any(kw in title for kw in ("brd", "business requirements", "architecture", "adr")):
            invoke_agent(
                "planning-agent",
                f"Confluence page updated: '{page.get('title')}' in space {space}. "
                f"URL: {page.get('_links', {}).get('webui', '')}. "
                f"Re-assess test strategy and maps based on this update.",
            )

    return jsonify({"status": "accepted"}), 202


@app.route("/webhooks/gcp-monitoring", methods=["POST"])
def gcp_monitoring_webhook() -> Response:
    """GCP Cloud Monitoring alert webhook (Pub/Sub push subscription)."""
    if not verify_pubsub_token(request.headers.get("Authorization", "")):
        abort(401, "Invalid Pub/Sub auth token")

    envelope = request.get_json(force=True)

    # Pub/Sub push envelope — `data` is base64-encoded JSON
    message = envelope.get("message", {})
    raw = message.get("data", "e30=")  # "e30=" is base64 for "{}"
    try:
        data = json.loads(base64.b64decode(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to decode Pub/Sub payload: %s", exc)
        return jsonify({"status": "invalid payload"}), 400

    incident = data.get("incident", {})
    severity = data.get("severity", "INFO")

    if severity in ("CRITICAL", "ERROR") or incident.get("state") == "open":
        doc = record_signal("gcp", data)
        invoke_agent(
            "incident-agent",
            with_signal(
                doc,
                f"GCP Cloud Monitoring alert fired: {incident.get('url', 'N/A')}. "
                f"Perform root cause analysis. Present findings for human confirmation "
                f"before generating incident ticket or regression test request.",
            ),
        )

    return jsonify({"status": "accepted"}), 202


@app.route("/health", methods=["GET"])
def health() -> Response:
    return jsonify({"status": "ok"}), 200


def _is_new_service_pr(pr: dict) -> bool:
    changed_files = pr.get("changed_files", 0)
    title = pr.get("title", "").lower()
    return changed_files > 10 and any(kw in title for kw in ("new service", "add service", "new repo"))


def _is_dependency_bump(pr: dict) -> bool:
    title = pr.get("title", "").lower()
    return any(kw in title for kw in ("bump", "upgrade", "update dependency", "dependabot"))


def _is_new_service_push(payload: dict) -> bool:
    return payload.get("created", False) and payload.get("ref", "").startswith("refs/heads/main")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
