#!/usr/bin/env bash
# QEaaS Scaffold — set up QE framework for a target repo
# Usage: ./scaffold.sh --mode <agentic|framework|both> --framework <pytest|golang|typescript|playwright|terratest|all> --target <path>

set -euo pipefail

MODE=""
FRAMEWORK=""
TARGET=""

usage() {
  cat <<EOF
Usage: ./scaffold.sh [options]

Options:
  --mode        agentic | framework | both
  --framework   pytest | golang | typescript | playwright | terratest | all
  --target      path to target repo (default: current directory)

Examples:
  # Agentic only (Claude Code agents + .qe/ maps)
  ./scaffold.sh --mode agentic --target ../identity-repo

  # Framework only (test scaffold, no agents)
  ./scaffold.sh --mode framework --framework pytest --target ../identity-repo

  # Both (framework scaffold + Claude Code agents on top)
  ./scaffold.sh --mode both --framework golang,terratest --target ../microservices-repo
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)      MODE="$2";      shift 2 ;;
    --framework) FRAMEWORK="$2"; shift 2 ;;
    --target)    TARGET="$2";    shift 2 ;;
    *)           usage ;;
  esac
done

[[ -z "$MODE" ]] && { echo "Error: --mode is required"; usage; }
TARGET="${TARGET:-.}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORKS_DIR="$SCRIPT_DIR/frameworks"

copy_framework() {
  local fw="$1"
  local dest="$TARGET"
  echo "  Copying $fw framework scaffold to $dest..."
  case "$fw" in
    pytest)
      cp -r "$FRAMEWORKS_DIR/pytest/." "$dest/tests-pytest/" 2>/dev/null || true
      echo "  ✓ pytest scaffold → $dest/tests-pytest/"
      ;;
    golang)
      cp -r "$FRAMEWORKS_DIR/golang/." "$dest/tests-go/" 2>/dev/null || true
      echo "  ✓ golang scaffold → $dest/tests-go/"
      ;;
    typescript)
      cp -r "$FRAMEWORKS_DIR/typescript/." "$dest/tests-ts/" 2>/dev/null || true
      echo "  ✓ typescript scaffold → $dest/tests-ts/"
      ;;
    playwright)
      cp -r "$FRAMEWORKS_DIR/playwright/." "$dest/tests-playwright/" 2>/dev/null || true
      echo "  ✓ playwright scaffold → $dest/tests-playwright/"
      ;;
    terratest)
      cp -r "$FRAMEWORKS_DIR/terratest/." "$dest/tests-infra/" 2>/dev/null || true
      echo "  ✓ terratest scaffold → $dest/tests-infra/"
      ;;
    *)
      echo "  Unknown framework: $fw (skipping)"
      ;;
  esac
}

copy_agentic() {
  echo "  Copying Claude Code agent templates..."

  # Detect repo type from target directory contents
  if ls "$TARGET"/**/*.py 2>/dev/null | head -1 | grep -q "\.py" || [[ -f "$TARGET/pyproject.toml" ]]; then
    REPO_TYPE="identity-repo"
  else
    REPO_TYPE="microservices-repo"
  fi

  mkdir -p "$TARGET/.claude/agents" "$TARGET/.qe" "$TARGET/.github/workflows"
  cp "$SCRIPT_DIR/repo-templates/$REPO_TYPE/.claude/agents/"* "$TARGET/.claude/agents/" 2>/dev/null || true
  # -R: the .qe OKF bundle has sub-folders (e.g. Domain-Map/) plus index.md and log.md.
  cp -R "$SCRIPT_DIR/repo-templates/$REPO_TYPE/.qe/." "$TARGET/.qe/" 2>/dev/null || true
  cp "$SCRIPT_DIR/repo-templates/$REPO_TYPE/.github/workflows/"* "$TARGET/.github/workflows/" 2>/dev/null || true

  echo "  ✓ Agent templates → $TARGET/.claude/agents/"
  echo "  ✓ QE maps (templates) → $TARGET/.qe/"
  echo "  ✓ GHA healer workflow → $TARGET/.github/workflows/"
  echo ""
  echo "  Next: run /plan-analysis in qe-as-a-service to populate .qe/ maps for this repo."
}

echo ""
echo "QEaaS Scaffold"
echo "=============="
echo "Mode:      $MODE"
echo "Framework: ${FRAMEWORK:-N/A}"
echo "Target:    $TARGET"
echo ""

case "$MODE" in
  framework)
    echo "Setting up framework scaffold..."
    if [[ "$FRAMEWORK" == "all" ]]; then
      for fw in pytest golang typescript playwright terratest; do
        copy_framework "$fw"
      done
    else
      IFS=',' read -ra FWS <<< "$FRAMEWORK"
      for fw in "${FWS[@]}"; do
        copy_framework "$(echo "$fw" | tr -d ' ')"
      done
    fi
    ;;
  agentic)
    echo "Setting up Claude Code agents..."
    copy_agentic
    ;;
  both)
    echo "Setting up framework scaffold + Claude Code agents..."
    if [[ "$FRAMEWORK" == "all" ]]; then
      for fw in pytest golang typescript playwright terratest; do
        copy_framework "$fw"
      done
    else
      IFS=',' read -ra FWS <<< "$FRAMEWORK"
      for fw in "${FWS[@]}"; do
        copy_framework "$(echo "$fw" | tr -d ' ')"
      done
    fi
    copy_agentic
    ;;
  *)
    echo "Error: unknown mode '$MODE'"
    usage
    ;;
esac

echo ""
echo "Done. Fill in REPLACE_WITH_* values in any config files before running tests."
