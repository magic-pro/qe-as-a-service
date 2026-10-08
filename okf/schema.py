"""QEaaS profile of OKF v0.1 — allowed types and required fields.

Human-readable version: okf/conventions.md. Keep the two in sync.
"""

from __future__ import annotations

# Knowledge the Planning Agent produces (maps, strategy).
MAP_TYPES = {
    "Data Type Map",
    "Identity Map",
    "Domain Map",
    "Test Strategy",
    "Infra Map",
}

# Normalised inbound signals (written by okf.normalize / webhooks/receiver.py).
SIGNAL_TYPES = {
    "Jira Story",
    "Jira Bug",
    "Jira Epic",
    "GitHub CI Failure",
    "GitHub Pull Request",
    "GCP Log Pattern",
}

# Agent outputs derived from a signal — must carry `derived_from`.
FINDING_TYPES = {
    "Map Update",
    "Coverage Gap",
    "Incident RCA",
    "Regression Test Request",
}

# Claude Code definitions — their frontmatter is shared with Claude Code.
TOOLING_TYPES = {"Agent", "Command"}

DOC_TYPES = {
    "Index",
    "Log",
    "Architecture",
    "Conventions",
    "Design Spec",
    "Implementation Plan",
}

ALLOWED_TYPES = MAP_TYPES | SIGNAL_TYPES | FINDING_TYPES | TOOLING_TYPES | DOC_TYPES

BASE_REQUIRED = ("type", "title", "description")

# `timestamp` is required everywhere except navigation docs and Claude Code tooling.
TIMESTAMP_EXEMPT = TOOLING_TYPES | {"Index", "Log"}

SIGNAL_REQUIRED = ("source", "key", "resource")
FINDING_REQUIRED = ("derived_from",)

PLACEHOLDER = "<!-- AGENT:"


def required_fields(doc_type: str) -> tuple[str, ...]:
    fields = list(BASE_REQUIRED)
    if doc_type not in TIMESTAMP_EXEMPT:
        fields.append("timestamp")
    if doc_type in SIGNAL_TYPES:
        fields.extend(SIGNAL_REQUIRED)
    if doc_type in FINDING_TYPES:
        fields.extend(FINDING_REQUIRED)
    return tuple(fields)
