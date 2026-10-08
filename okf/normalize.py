"""Normalise raw GitHub, Jira and GCP Log Explorer payloads into OKF signal docs.

Every inbound signal becomes one markdown file with typed frontmatter, so all
agents consume the same shape regardless of where the signal came from.
PII is masked before anything is written.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from okf.frontmatter import render

# Mirrors finance_constraints.pii_fields + audit ip_address in target-repos/*.json.
DEFAULT_PII_FIELDS = (
    "customer_name",
    "email",
    "dob",
    "account_number",
    "phone",
    "ip_address",
    "iban",
    "card_number",
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_PAN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"\+\d{1,3}[ -]?\d{3,4}[ -]?\d{3,4}[ -]?\d{0,4}\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def redact(text: str) -> str:
    """Mask PII patterns in free text. Order matters: IBAN before PAN."""
    text = _EMAIL.sub("<email>", text)
    text = _IBAN.sub("<iban>", text)
    text = _IPV4.sub("<ip>", text)
    text = _PHONE.sub("<phone>", text)
    text = _PAN.sub("<pan>", text)
    return text


def redact_fields(obj: Any, pii_fields: Iterable[str] = DEFAULT_PII_FIELDS) -> Any:
    """Recursively replace values of PII-named keys, and redact remaining strings."""
    pii = {f.lower() for f in pii_fields}
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if k.lower() in pii else redact_fields(v, pii))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_fields(v, pii) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


@dataclass
class SignalDoc:
    meta: dict[str, Any]
    body: str
    relpath: str  # path inside the signals bundle, e.g. "jira/PAY-214.md"

    def text(self) -> str:
        return render(self.meta, self.body)

    def write(self, out_dir: str | Path) -> Path:
        path = Path(out_dir) / self.relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.text(), encoding="utf-8")
        return path


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "signal"


def _iso(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Jira uses "2026-09-20T10:15:00.000+0000"; normalise to UTC Z.
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(value.replace("Z", "+0000"), fmt)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return value


def _one_line(text: str, limit: int = 160) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


# ---------------------------------------------------------------- Jira


def adf_to_markdown(node: Any, depth: int = 0) -> str:
    """Convert Atlassian Document Format (Jira Cloud rich text) to markdown."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    kind = node.get("type")
    children = node.get("content", [])
    if kind == "text":
        return node.get("text", "")
    if kind == "hardBreak":
        return "\n"
    inner = "".join(adf_to_markdown(c, depth) for c in children)
    if kind == "heading":
        return "#" * (node.get("attrs", {}).get("level", 2) + 1) + " " + inner + "\n\n"
    if kind == "paragraph":
        return inner + "\n\n"
    if kind in ("bulletList", "orderedList"):
        items = []
        for i, item in enumerate(children, 1):
            marker = f"{i}." if kind == "orderedList" else "-"
            text = "".join(adf_to_markdown(c, depth + 1) for c in item.get("content", []))
            items.append("  " * depth + f"{marker} {text.strip()}")
        return "\n".join(items) + "\n\n"
    if kind == "codeBlock":
        return "```\n" + inner + "\n```\n\n"
    return inner


_JIRA_TYPES = {"Story": "Jira Story", "Bug": "Jira Bug", "Epic": "Jira Epic"}


def jira_to_okf(payload: dict[str, Any], base_url: str = "") -> SignalDoc:
    issue = payload.get("issue", {})
    f = issue.get("fields", {})
    key = issue.get("key", "UNKNOWN")
    issue_type = f.get("issuetype", {}).get("name", "Story")
    summary = redact(f.get("summary", ""))
    desc = f.get("description")
    body_desc = adf_to_markdown(desc) if isinstance(desc, dict) else (desc or "")
    body_desc = redact(body_desc).strip()

    links = []
    for link in f.get("issuelinks", []):
        other = link.get("outwardIssue") or link.get("inwardIssue") or {}
        rel = link.get("type", {}).get("outward" if "outwardIssue" in link else "inward", "relates to")
        if other.get("key"):
            links.append(f"- {rel} `{other['key']}`")

    resource = issue.get("self", "")
    if base_url:
        resource = f"{base_url.rstrip('/')}/browse/{key}"

    labels = f.get("labels", [])
    components = [c.get("name", "") for c in f.get("components", [])]
    meta: dict[str, Any] = OrderedDict()
    meta["type"] = _JIRA_TYPES.get(issue_type, "Jira Story")
    meta["title"] = f"{key}: {summary}"
    meta["description"] = _one_line(summary)
    meta["resource"] = resource
    meta["tags"] = sorted({"jira", issue_type.lower(), *labels, *[_slug(c) for c in components]})
    meta["timestamp"] = _iso(f.get("updated") or f.get("created"))
    meta["source"] = "jira"
    meta["key"] = key
    meta["event"] = payload.get("webhookEvent", "")
    meta["status"] = f.get("status", {}).get("name", "")
    meta["priority"] = f.get("priority", {}).get("name", "")
    if f.get("customfield_brd"):
        meta["brd"] = f["customfield_brd"]

    body = [f"# {key} — {summary}", ""]
    body.append(f"**Type:** {issue_type} · **Status:** {meta['status']} · **Priority:** {meta['priority']}")
    if components:
        body.append(f"**Components:** {', '.join(components)}")
    body += ["", "## Description", "", body_desc or "_(empty)_", ""]
    if links:
        body += ["## Linked issues", "", *links, ""]
    return SignalDoc(dict(meta), "\n".join(body), f"jira/{key}.md")


# ---------------------------------------------------------------- GitHub

_FAIL_LINE = re.compile(r"(--- FAIL|^FAIL|Error Trace|Error:|expected|actual|panic:)", re.I)


def _failing_excerpt(log: str, limit: int = 40) -> str:
    lines = [l.rstrip() for l in log.splitlines() if _FAIL_LINE.search(l.strip())]
    return "\n".join(lines[:limit])


def github_to_okf(event: str, payload: dict[str, Any], log: str | None = None) -> SignalDoc:
    repo = payload.get("repository", {}).get("full_name", "unknown/unknown")
    repo_name = repo.split("/")[-1]

    if event == "workflow_run":
        run = payload.get("workflow_run", {})
        run_id = run.get("id", 0)
        branch = run.get("head_branch", "")
        sha = run.get("head_sha", "")[:12]
        title = f"CI failure: {run.get('name', 'workflow')} on {repo_name}@{branch}"
        meta: dict[str, Any] = OrderedDict()
        meta["type"] = "GitHub CI Failure"
        meta["title"] = title
        meta["description"] = _one_line(
            f"Workflow '{run.get('name', '')}' concluded {run.get('conclusion', '')} "
            f"on {branch} ({sha}): {run.get('display_title', '')}"
        )
        meta["resource"] = run.get("html_url", "")
        meta["tags"] = ["github", "ci", repo_name]
        meta["timestamp"] = _iso(run.get("updated_at") or run.get("created_at"))
        meta["source"] = "github"
        meta["key"] = f"{repo}#run-{run_id}"
        meta["repo"] = repo
        meta["event"] = event
        meta["conclusion"] = run.get("conclusion", "")
        prs = [p.get("number") for p in run.get("pull_requests", []) if p.get("number")]
        if prs:
            meta["pull_requests"] = prs

        body = [f"# {title}", ""]
        body.append(f"- **Commit:** `{sha}` — {redact(run.get('display_title', ''))}")
        body.append(f"- **Branch:** `{branch}`")
        if prs:
            body.append("- **Pull requests:** " + ", ".join(f"#{n}" for n in prs))
        jobs = payload.get("failed_jobs", [])
        if jobs:
            body += ["", "## Failed jobs", ""]
            for j in jobs:
                body.append(f"- `{j.get('name', '')}` → step `{j.get('failed_step', '')}`")
        if log:
            excerpt = _failing_excerpt(redact(log))
            if excerpt:
                body += ["", "## Failing test output (excerpt)", "", "```", excerpt, "```"]
        return SignalDoc(dict(meta), "\n".join(body) + "\n", f"github/{repo_name}-run-{run_id}.md")

    if event == "pull_request":
        pr = payload.get("pull_request", {})
        number = pr.get("number", 0)
        meta = OrderedDict()
        meta["type"] = "GitHub Pull Request"
        meta["title"] = f"PR #{number}: {redact(pr.get('title', ''))}"
        meta["description"] = _one_line(redact(pr.get("title", "")))
        meta["resource"] = pr.get("html_url", "")
        meta["tags"] = ["github", "pull-request", repo_name]
        meta["timestamp"] = _iso(pr.get("updated_at") or pr.get("created_at"))
        meta["source"] = "github"
        meta["key"] = f"{repo}#pr-{number}"
        meta["repo"] = repo
        meta["event"] = f"{event}.{payload.get('action', '')}"
        body = [f"# PR #{number} — {redact(pr.get('title', ''))}", "", redact(pr.get("body") or "_(no description)_"), ""]
        files = payload.get("changed_files_list", [])
        if files:
            body += ["## Changed files", "", *[f"- `{p}`" for p in files], ""]
        return SignalDoc(dict(meta), "\n".join(body), f"github/{repo_name}-pr-{number}.md")

    raise ValueError(f"unsupported GitHub event for OKF normalisation: {event}")


# ---------------------------------------------------------------- GCP Log Explorer


def _entry_pattern(entry: dict[str, Any]) -> str:
    jp = entry.get("jsonPayload") or {}
    return jp.get("event") or jp.get("message") or entry.get("textPayload", "")[:80] or "unknown"


def gcp_logs_to_okf(data: dict[str, Any]) -> SignalDoc:
    """`data` holds an optional Cloud Monitoring `incident` and/or Log Explorer `entries`."""
    incident = data.get("incident", {})
    entries = [redact_fields(e) for e in data.get("entries", [])]

    groups: "OrderedDict[tuple[str, str, str], dict[str, Any]]" = OrderedDict()
    for e in entries:
        service = e.get("resource", {}).get("labels", {}).get("service_name", "unknown")
        k = (e.get("severity", "DEFAULT"), service, _entry_pattern(e))
        g = groups.setdefault(k, {"count": 0, "first": e.get("timestamp"), "last": e.get("timestamp"), "traces": [], "sample": e})
        g["count"] += 1
        ts = e.get("timestamp")
        if ts and (not g["first"] or ts < g["first"]):
            g["first"] = ts
        if ts and (not g["last"] or ts > g["last"]):
            g["last"] = ts
        tr = e.get("trace")
        if tr and len(g["traces"]) < 3:
            g["traces"].append(tr.split("/")[-1])

    top = max(groups.items(), key=lambda kv: kv[1]["count"]) if groups else None
    condition = incident.get("condition", {}).get("displayName") or incident.get("condition_name", "")
    headline = condition or (top[0][2] if top else "log pattern")
    services = sorted({k[1] for k in groups}) or [incident.get("resource", {}).get("labels", {}).get("service_name", "unknown")]
    severity = data.get("severity") or (top[0][0] if top else "INFO")
    last_ts = max((g["last"] for g in groups.values() if g["last"]), default=None)
    incident_id = incident.get("incident_id", "")

    meta: dict[str, Any] = OrderedDict()
    meta["type"] = "GCP Log Pattern"
    meta["title"] = f"{headline} ({', '.join(services)})"
    meta["description"] = _one_line(
        f"{severity} alert — {sum(g['count'] for g in groups.values())} log entries across "
        f"{len(groups)} pattern(s); top: {top[0][2] if top else 'n/a'}"
    )
    meta["resource"] = incident.get("url", "") or "https://console.cloud.google.com/logs/query"
    meta["tags"] = sorted({"gcp", "logs", severity.lower(), *services})
    meta["timestamp"] = _iso(last_ts or incident.get("started_at"))
    meta["source"] = "gcp"
    meta["key"] = incident_id or f"logs-{_slug(headline)}"
    meta["severity"] = severity
    meta["services"] = services
    if data.get("log_filter"):
        meta["log_filter"] = data["log_filter"]

    body = [f"# {headline}", ""]
    if incident:
        body += [
            "## Alert",
            "",
            f"- **Policy:** {incident.get('policy_name', '')}",
            f"- **Condition:** {condition}",
            f"- **State:** {incident.get('state', '')} · **Started:** {incident.get('started_at', '')}",
            f"- **Summary:** {redact(incident.get('summary', ''))}",
            "",
        ]
    if groups:
        body += ["## Log patterns", "", "| Severity | Service | Pattern | Count | First seen | Last seen |", "|---|---|---|---|---|---|"]
        for (sev, svc, pat), g in groups.items():
            body.append(f"| {sev} | {svc} | `{pat}` | {g['count']} | {g['first']} | {g['last']} |")
        body += ["", "## Sample entries", ""]
        for (sev, svc, pat), g in groups.items():
            jp = g["sample"].get("jsonPayload", {})
            fields = ", ".join(f"`{k}={v}`" for k, v in jp.items() if k not in ("message",))
            body.append(f"- **{pat}** — {redact(str(jp.get('message', '')))}  ")
            body.append(f"  fields: {fields}  ")
            if g["traces"]:
                body.append(f"  traces: {', '.join('`' + t + '`' for t in g['traces'])}")
        body.append("")
    else:
        body += ["_No log entries attached — query Log Explorer with the alert's resource and window._", ""]

    rel = f"gcp/{_slug(meta['key'])}.md"
    return SignalDoc(dict(meta), "\n".join(body), rel)


def normalize(source: str, payload: dict[str, Any], **kwargs: Any) -> SignalDoc:
    if source == "jira":
        return jira_to_okf(payload, base_url=kwargs.get("base_url", ""))
    if source == "github":
        return github_to_okf(kwargs["event"], payload, log=kwargs.get("log"))
    if source == "gcp":
        return gcp_logs_to_okf(payload)
    raise ValueError(f"unknown source: {source}")
