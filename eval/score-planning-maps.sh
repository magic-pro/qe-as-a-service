#!/usr/bin/env bash
# eval/score-planning-maps.sh — Rule-based conformance scorecard for Planning Agent QE maps.
# Usage: eval/score-planning-maps.sh <data-type-map.md> [identity-map.md]
# Output: markdown scorecard (append to artifacts/test-strategy.md or print to stdout).
# Bash 3.2 compatible (macOS default shell).
set -uo pipefail

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "Usage: $0 <data-type-map.md> [identity-map.md]" >&2
    exit 1
fi

DATA_MAP="$1"
IDENTITY_MAP="${2:-}"
fail=0
warn=0

row() { printf '| %-46s | %-30s | %s |\n' "$1" "$2" "$3"; }

count_in_file() {
    local pattern="$1" file="$2"
    grep -ciE "$pattern" "$file" 2>/dev/null || true
}

echo "## QE Eval Scorecard — Planning Maps"
echo ""
echo "| Metric | Value | Status |"
echo "|---|---|---|"

# 1. Float/double type violations in data-type-map
float_count=$(count_in_file '\bfloat\b|\bdouble\b|\bfloat64\b|\bFloat64\b|\bDouble\b' "$DATA_MAP")
if [ "$float_count" -gt 0 ]; then
    row "Float/double type violations" "$float_count occurrences" "FAIL"; fail=1
else
    row "Float/double type violations" "0" "PASS"
fi

# 2. Decimal/BigDecimal enforcement for monetary fields
decimal_count=$(count_in_file '\bDecimal\b|\bBigDecimal\b' "$DATA_MAP")
if [ "$decimal_count" -gt 0 ]; then
    row "Decimal type enforcement" "$decimal_count references" "PASS"
else
    row "Decimal type enforcement" "0 — no Decimal type found" "WARN"; warn=1
fi

# 3. Boundary conditions coverage
# Count boundary-related keywords vs total table rows as a rough proxy
boundary_count=$(count_in_file '\bnull\b|\bempty\b|\bmin\b|\bmax\b|\bnegative\b|\bboundary\b|\bzero\b|\bduplicate\b|\bfuture.dated\b' "$DATA_MAP")
table_rows=$(grep -c '|' "$DATA_MAP" 2>/dev/null || true)
if [ "$table_rows" -gt 0 ]; then
    boundary_pct=$(awk "BEGIN { printf \"%d\", ($boundary_count * 100) / $table_rows }")
else
    boundary_pct=0
fi
if [ "$boundary_pct" -ge 80 ]; then
    row "Boundary conditions coverage" "${boundary_pct}% (${boundary_count} refs / ${table_rows} rows)" "PASS"
elif [ "$boundary_pct" -ge 50 ]; then
    row "Boundary conditions coverage" "${boundary_pct}% (${boundary_count} refs / ${table_rows} rows)" "WARN"; warn=1
else
    row "Boundary conditions coverage" "${boundary_pct}% (${boundary_count} refs / ${table_rows} rows)" "FAIL"; fail=1
fi

# 4. Finance-specific flags
finance_count=$(count_in_file '\bKYC\b|\bAML\b|\bregulat\b|\baudit\b|\bfraud\b|\bPII\b|\bcompliance\b|\bSWIFT\b|\bIBAN\b|\bBSB\b' "$DATA_MAP")
if [ "$finance_count" -ge 3 ]; then
    row "Finance flags (KYC/AML/audit/PII/fraud)" "$finance_count references" "PASS"
elif [ "$finance_count" -ge 1 ]; then
    row "Finance flags (KYC/AML/audit/PII/fraud)" "$finance_count references" "WARN"; warn=1
else
    row "Finance flags (KYC/AML/audit/PII/fraud)" "0" "FAIL"; fail=1
fi

# 5. Risk levels assigned
risk_count=$(count_in_file '\bHigh\b|\bMedium\b|\bLow\b|\bCritical\b' "$DATA_MAP")
if [ "$risk_count" -gt 0 ]; then
    row "Risk levels assigned" "$risk_count labels" "PASS"
else
    row "Risk levels assigned" "0 — no risk labels found" "FAIL"; fail=1
fi

# 6. BRD traceability
brd_count=$(count_in_file 'BRD[-_]|REQ[-_]|requirement' "$DATA_MAP")
if [ "$brd_count" -gt 0 ]; then
    row "BRD/requirement traceability" "$brd_count references" "PASS"
else
    row "BRD/requirement traceability" "0 — no BRD refs" "WARN"; warn=1
fi

# 7. Identity map metrics (if provided)
if [ -n "$IDENTITY_MAP" ] && [ -f "$IDENTITY_MAP" ]; then
    kyc_aml_count=$(count_in_file '\bKYC\b|\bAML\b' "$IDENTITY_MAP")
    fraud_count=$(count_in_file '\bfraud\b|\bvelocity\b' "$IDENTITY_MAP")
    scenario_count=$(grep -cE '^###|^- \*\*' "$IDENTITY_MAP" 2>/dev/null || true)

    if [ "$kyc_aml_count" -gt 0 ]; then
        row "KYC/AML scenarios (identity map)" "$kyc_aml_count references" "PASS"
    else
        row "KYC/AML scenarios (identity map)" "0" "FAIL"; fail=1
    fi
    if [ "$fraud_count" -gt 0 ]; then
        row "Fraud signal scenarios (identity map)" "$fraud_count references" "PASS"
    else
        row "Fraud signal scenarios (identity map)" "0" "WARN"; warn=1
    fi
    row "Scenario sections in identity map" "$scenario_count" "$([ "$scenario_count" -ge 3 ] && echo PASS || echo WARN)"
fi

echo ""
if [ "$fail" -gt 0 ]; then
    echo "**Overall: FAIL** — one or more required checks did not pass. Resolve before merging."
    exit 1
elif [ "$warn" -gt 0 ]; then
    echo "**Overall: WARN** — review flagged items before merging."
else
    echo "**Overall: PASS**"
fi
