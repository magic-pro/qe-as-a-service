#!/usr/bin/env bash
# eval/score-healer-report.sh — Rule-based conformance scorecard for Test Healer reports.
# Usage: eval/score-healer-report.sh <healer-report.md>
# Output: markdown scorecard (append to healer report PR description).
# Bash 3.2 compatible (macOS default shell).
set -uo pipefail

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "Usage: $0 <healer-report.md>" >&2
    exit 1
fi

REPORT="$1"
fail=0
warn=0

row() { printf '| %-46s | %-30s | %s |\n' "$1" "$2" "$3"; }

content=$(cat "$REPORT")
cnt() { printf '%s' "$content" | grep -c "$@" || true; }
has() { printf '%s' "$content" | grep -q "$@"; }

echo "## QE Eval Scorecard — Test Healer"
echo ""
echo "| Metric | Value | Status |"
echo "|---|---|---|"

# 1. Parse auto-fixed and escalated counts from the healer report header
# Expects lines like: "3 total — 2 auto-fixed, 1 escalated" (from the Output Format)
auto_fixed=$(printf '%s' "$content" | grep -oiE '[0-9]+ auto.fix' | grep -oE '[0-9]+' | head -1 || true)
escalated=$(printf '%s' "$content" | grep -oiE '[0-9]+ escalat' | grep -oE '[0-9]+' | head -1 || true)
auto_fixed=${auto_fixed:-0}
escalated=${escalated:-0}
total=$(( auto_fixed + escalated ))

if [ "$total" -gt 0 ]; then
    fix_rate=$(awk "BEGIN { printf \"%d\", ($auto_fixed * 100) / $total }")
    if [ "$fix_rate" -ge 50 ]; then
        row "Auto-fix rate" "${fix_rate}% (${auto_fixed} / ${total})" "PASS"
    else
        row "Auto-fix rate" "${fix_rate}% (${auto_fixed} / ${total})" "WARN"; warn=1
    fi
    row "Escalated findings" "$escalated" "PASS"
else
    row "Auto-fix rate" "N/A (no findings processed)" "PASS"
    row "Escalated findings" "0" "PASS"
fi

# 2. Finance-critical findings count (informational)
finance_count=$(cnt -iE 'finance.critical|Finance Flag|DMI_BIGDECIMAL|java:S2111|java:S2184|float.*amount|double.*balance')
row "Finance-critical findings identified" "$finance_count" "PASS"

# 3. NOSONAR / SuppressWarnings — hard prohibition
suppress_count=$(cnt -iE '@SuppressWarnings|//NOSONAR|# noqa|# type: ignore.*finance')
if [ "$suppress_count" -gt 0 ]; then
    row "Suppressions used (NOSONAR/SuppressWarnings)" "$suppress_count — VIOLATION" "FAIL"; fail=1
else
    row "Suppressions used (NOSONAR/SuppressWarnings)" "0" "PASS"
fi

# 4. Regression findings auto-fixed (must always be escalated, never auto-fixed)
# Look for "Regression" in the Auto-fixed table section
auto_fix_section=$(printf '%s' "$content" | sed -n '/### Auto-fixed/,/### Escalated/p')
regression_autofixed=$(printf '%s' "$auto_fix_section" | grep -ciE 'regression' || true)
if [ "$regression_autofixed" -gt 0 ]; then
    row "Regression findings auto-fixed (VIOLATION)" "$regression_autofixed" "FAIL"; fail=1
else
    row "Regression findings auto-fixed" "0" "PASS"
fi

# 5. Decimal→float weakening in fixes
decimal_weakened=$(cnt -iE 'changed.*float|float.*instead.*Decimal|Decimal.*to.*float|replaced.*Decimal.*float')
if [ "$decimal_weakened" -gt 0 ]; then
    row "Finance type weakening (Decimal→float) in fixes" "$decimal_weakened" "FAIL"; fail=1
else
    row "Finance type weakening in fixes" "0" "PASS"
fi

# 6. KYC/AML tests removed (should never happen)
kyc_removed=$(cnt -iE 'removed.*KYC|removed.*AML|deleted.*kyc|deleted.*aml')
if [ "$kyc_removed" -gt 0 ]; then
    row "KYC/AML tests removed" "$kyc_removed — VIOLATION" "FAIL"; fail=1
else
    row "KYC/AML tests removed" "0" "PASS"
fi

# 7. PR raised
if has -iE 'PR raised|pull request raised|\*\*PR'; then
    row "PR raised for fixes" "Yes" "PASS"
else
    row "PR raised for fixes" "Not detected in report" "WARN"; warn=1
fi

echo ""
if [ "$fail" -gt 0 ]; then
    echo "**Overall: FAIL** — finance constraint or policy violation. Do not merge."
    exit 1
elif [ "$warn" -gt 0 ]; then
    echo "**Overall: WARN** — review flagged items before merging."
else
    echo "**Overall: PASS**"
fi
