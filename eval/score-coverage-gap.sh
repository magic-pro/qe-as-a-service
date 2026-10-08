#!/usr/bin/env bash
# eval/score-coverage-gap.sh — Rule-based conformance scorecard for Coverage Gap reports.
# Usage: eval/score-coverage-gap.sh <coverage-gap-report.md>
# Output: markdown scorecard (append to artifacts/coverage-gap-report.md).
# Bash 3.2 compatible (macOS default shell).
set -uo pipefail

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "Usage: $0 <coverage-gap-report.md>" >&2
    exit 1
fi

REPORT="$1"
fail=0
warn=0

row() { printf '| %-46s | %-30s | %s |\n' "$1" "$2" "$3"; }

content=$(cat "$REPORT")
cnt() { printf '%s' "$content" | grep -c "$@" || true; }
has() { printf '%s' "$content" | grep -q "$@"; }

echo "## QE Eval Scorecard — Coverage Agent"
echo ""
echo "| Metric | Value | Status |"
echo "|---|---|---|"

# 1. Gap counts by priority
critical_gaps=$(cnt -iE '\| *Critical')
high_gaps=$(cnt -iE '\| *High')
medium_gaps=$(cnt -iE '\| *Medium')
total_gaps=$(( critical_gaps + high_gaps + medium_gaps ))

row "Critical gaps identified" "$critical_gaps" "PASS"
row "High priority gaps" "$high_gaps" "PASS"
row "Medium priority gaps" "$medium_gaps" "PASS"

# 2. Test creation requests — every Critical gap must have one
test_requests=$(cnt -iE 'Test Creation Request|gh workflow run|workflow_dispatch')
if [ "$critical_gaps" -gt 0 ] && [ "$test_requests" -eq 0 ]; then
    row "Test creation requests raised" "0 / $critical_gaps critical gaps" "FAIL"; fail=1
elif [ "$test_requests" -gt 0 ]; then
    row "Test creation requests raised" "$test_requests" "PASS"
else
    row "Test creation requests raised" "N/A (no gaps)" "PASS"
fi

# 3. Finance-critical gaps must be addressed
finance_gaps=$(cnt -iE '\bKYC\b|\bAML\b|\bmonetary\b|\bdecimal\b|\baudit trail\b|\bfraud\b|\bregulatory\b')
if [ "$finance_gaps" -gt 0 ]; then
    # Check if finance gaps have associated test requests
    # Heuristic: if finance_gaps > 0 and test_requests > 0, assume addressed
    if [ "$test_requests" -gt 0 ]; then
        row "Finance-critical gaps addressed" "$finance_gaps gaps, $test_requests requests raised" "PASS"
    else
        row "Finance-critical gaps addressed" "$finance_gaps gaps, 0 requests raised" "FAIL"; fail=1
    fi
else
    row "Finance-critical gap areas" "0 identified — verify scan completeness" "WARN"; warn=1
fi

# 4. New float/double fields detected in production
float_in_prod=$(cnt -iE 'float.*production|double.*production|float.*new field|float64.*detected')
if [ "$float_in_prod" -gt 0 ]; then
    row "Float/double fields detected in production" "$float_in_prod — escalate immediately" "FAIL"; fail=1
else
    row "Float/double fields detected in production" "0" "PASS"
fi

# 5. Map updates needed vs PRs raised
map_updates_needed=$(cnt -iE 'data.type.map.*update|identity.map.*update|map.*needs update|update.*map')
map_prs_raised=$(cnt -iE '\[QEaaS Coverage\]|coverage.*PR raised|PR.*map update')
if [ "$map_updates_needed" -gt 0 ] && [ "$map_prs_raised" -eq 0 ]; then
    row "Map update PRs raised" "0 / $map_updates_needed updates needed" "WARN"; warn=1
elif [ "$map_updates_needed" -gt 0 ]; then
    row "Map update PRs raised" "$map_prs_raised / $map_updates_needed updates" "PASS"
else
    row "Map update PRs raised" "N/A (no updates needed)" "PASS"
fi

# 6. Workflow run URL recorded (audit trail)
if has -iE 'workflow run|run URL|actions/runs'; then
    row "Workflow run URL in audit trail" "Present" "PASS"
else
    row "Workflow run URL in audit trail" "Not found" "WARN"; warn=1
fi

echo ""
if [ "$fail" -gt 0 ]; then
    echo "**Overall: FAIL** — critical gaps or finance violations unaddressed. Do not merge without resolution."
    exit 1
elif [ "$warn" -gt 0 ]; then
    echo "**Overall: WARN** — review flagged items before merging."
else
    echo "**Overall: PASS**"
fi
