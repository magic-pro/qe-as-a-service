#!/usr/bin/env bash
# eval/run-all.sh — Run all QE eval scorers against current repo artifacts.
# Usage: eval/run-all.sh [--identity-repo <path>] [--microservices-repo <path>]
# Run from qe-as-a-service root.
# Bash 3.2 compatible.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IDENTITY_REPO="${IDENTITY_REPO_PATH:-}"
MICROSERVICES_REPO="${MICROSERVICES_REPO_PATH:-}"

# Parse flags
while [ $# -gt 0 ]; do
    case "$1" in
        --identity-repo)     IDENTITY_REPO="$2";     shift 2 ;;
        --microservices-repo) MICROSERVICES_REPO="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

pass_count=0
fail_count=0
warn_count=0

run_scorer() {
    local label="$1"; shift
    echo ""
    echo "---"
    echo "### $label"
    echo ""
    if "$@"; then
        pass_count=$(( pass_count + 1 ))
    else
        local rc=$?
        if [ "$rc" -eq 1 ]; then
            fail_count=$(( fail_count + 1 ))
        else
            warn_count=$(( warn_count + 1 ))
        fi
    fi
}

echo "# QE Eval — Full Run"
echo "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# Planning maps (from identity-repo if available)
if [ -n "$IDENTITY_REPO" ] && [ -f "$IDENTITY_REPO/.qe/data-type-map.md" ]; then
    id_map="$IDENTITY_REPO/.qe/identity-map.md"
    [ -f "$id_map" ] || id_map=""
    run_scorer "Planning Maps — identity-repo" \
        "$SCRIPT_DIR/score-planning-maps.sh" "$IDENTITY_REPO/.qe/data-type-map.md" $id_map
fi

if [ -n "$MICROSERVICES_REPO" ] && [ -f "$MICROSERVICES_REPO/.qe/data-type-map.md" ]; then
    ms_id_map="$MICROSERVICES_REPO/.qe/identity-map.md"
    [ -f "$ms_id_map" ] || ms_id_map=""
    run_scorer "Planning Maps — microservices-repo" \
        "$SCRIPT_DIR/score-planning-maps.sh" "$MICROSERVICES_REPO/.qe/data-type-map.md" $ms_id_map
fi

# Coverage gap report
if [ -f "$REPO_ROOT/artifacts/coverage-gap-report.md" ]; then
    run_scorer "Coverage Gap Report" \
        "$SCRIPT_DIR/score-coverage-gap.sh" "$REPO_ROOT/artifacts/coverage-gap-report.md"
fi

# Generated tests in target repos
if [ -n "$IDENTITY_REPO" ] && [ -d "$IDENTITY_REPO/tests" ]; then
    run_scorer "Generated Tests — identity-repo (python)" \
        "$SCRIPT_DIR/score-generated-tests.sh" "$IDENTITY_REPO/tests" python
fi

if [ -n "$MICROSERVICES_REPO" ] && [ -d "$MICROSERVICES_REPO" ]; then
    # Find Go test files
    if find "$MICROSERVICES_REPO" -name '*_test.go' 2>/dev/null | grep -q .; then
        run_scorer "Generated Tests — microservices-repo (go)" \
            "$SCRIPT_DIR/score-generated-tests.sh" "$MICROSERVICES_REPO" go
    fi
fi

echo ""
echo "---"
echo ""
echo "## Summary"
echo "| Stage | Result |"
echo "|---|---|"
echo "| PASS | $pass_count |"
echo "| WARN | $warn_count |"
echo "| FAIL | $fail_count |"
echo ""
if [ "$fail_count" -gt 0 ]; then
    echo "**Overall: FAIL** — $fail_count scorer(s) failed."
    exit 1
elif [ "$warn_count" -gt 0 ]; then
    echo "**Overall: WARN** — $warn_count scorer(s) need review."
else
    echo "**Overall: PASS**"
fi
