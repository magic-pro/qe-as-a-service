#!/usr/bin/env python3
"""Stage only the files needed by the agent image before Cloud Build upload."""

import fnmatch
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TRACKED_INPUTS = (
    ".claude/agents", ".claude/commands", ".claude/settings.json",
    ".github/agents", "CLAUDE.md", "artifacts", "docs", "frameworks",
    "okf", "repo-templates", "target-repos", "twin",
)
SERVICE_INPUTS = (
    "agent_service/Dockerfile", "agent_service/requirements.txt",
    "agent_service/__init__.py", "agent_service/app.py", "agent_service/stdio.py",
    "agent_service/a2a_auth.py", "agent_service/contracts.py",
    "agent_service/result_log.py", "agent_service/mcp-stdio.example.json",
    "docs/agent-service.md",
)
EXCLUDED_NAMES = (
    ".mcp.json", ".env", ".env.*", "*.pem", "*.key", "*.log",
    "service-account*.json", "gcp-sa*.json",
)
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "ci-output", "knowledge"}


def stage_inputs(root: Path, destination: Path) -> None:
    root = root.resolve()
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--", *TRACKED_INPUTS]
    ).decode("utf-8").split("\0")
    inputs = set(filter(None, tracked)) | set(SERVICE_INPUTS)
    for relative in sorted(inputs):
        parts = Path(relative).parts
        if (any(part in EXCLUDED_DIRS for part in parts[:-1])
                or any(fnmatch.fnmatchcase(parts[-1], pattern) for pattern in EXCLUDED_NAMES)):
            continue
        source = root / relative
        if source.is_symlink() or not source.resolve().is_relative_to(root) or not source.is_file():
            raise ValueError(f"Build input is missing or unsafe: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)


def main() -> None:
    root, project, image, config, ignore = sys.argv[1:]
    with tempfile.TemporaryDirectory(prefix="qe-agent-build-") as directory:
        stage_inputs(Path(root), Path(directory))
        subprocess.run(
            ["gcloud", "builds", "submit", "--config", config, "--ignore-file", ignore,
             "--substitutions", f"_IMAGE={image}", "--project", project, directory],
            check=True,
        )


if __name__ == "__main__":
    main()
