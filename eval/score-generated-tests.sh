#!/usr/bin/env bash
# eval/score-generated-tests.sh — Rule-based conformance scorecard for generated test files.
# Usage: eval/score-generated-tests.sh <test-dir-or-file> [go|python]
# Output: markdown scorecard (include in PR description or generation report).
# Bash 3.2 compatible (macOS default shell).
set -uo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <test-dir-or-file> [go|python]" >&2
    exit 1
fi

TARGET="$1"
LANG="${2:-}"
fail=0
warn=0

row() { printf '| %-46s | %-30s | %s |\n' "$1" "$2" "$3"; }

# Auto-detect language
if [ -z "$LANG" ]; then
    if find "$TARGET" -name '*_test.go' 2>/dev/null | grep -q .; then
        LANG="go"
    elif find "$TARGET" \( -name 'test_*.py' -o -name '*_test.py' \) 2>/dev/null | grep -q .; then
        LANG="python"
    else
        echo "Error: no Go or Python test files found in '$TARGET'" >&2
        exit 1
    fi
fi

# Gather all test file content into a single variable
content=""
if [ -f "$TARGET" ]; then
    content=$(cat "$TARGET")
elif [ -d "$TARGET" ]; then
    if [ "$LANG" = "go" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] && content="$content$(cat "$f")
"
        done <<FILES
$(find "$TARGET" -name '*_test.go' 2>/dev/null)
FILES
    else
        while IFS= read -r f; do
            [ -n "$f" ] && content="$content$(cat "$f")
"
        done <<FILES
$(find "$TARGET" \( -name 'test_*.py' -o -name '*_test.py' \) 2>/dev/null)
FILES
    fi
fi

if [ -z "$content" ]; then
    echo "Error: no test content found in '$TARGET'" >&2
    exit 1
fi

# Strip comments for float-in-code checks
if [ "$LANG" = "go" ]; then
    code_only=$(printf '%s' "$content" | sed 's|//.*$||')
else
    code_only=$(printf '%s' "$content" | sed 's|#.*$||')
fi

has()      { printf '%s' "$content"   | grep -q "$@"; }
has_code() { printf '%s' "$code_only" | grep -q "$@"; }
cnt()      { printf '%s' "$content"   | grep -c "$@" || true; }

echo "## QE Eval Scorecard — Generated Tests ($LANG)"
echo ""
echo "| Metric | Value | Status |"
echo "|---|---|---|"

# 1. Test function count
if [ "$LANG" = "go" ]; then
    test_count=$(cnt -E '^func Test')
else
    test_count=$(cnt -E '^def test_')
fi
if [ "$test_count" -gt 0 ]; then
    row "Test functions generated" "$test_count" "PASS"
else
    row "Test functions generated" "0" "FAIL"; fail=1
fi

# 2. Traceability tags
for tag in "BRD-REQ" "JIRA"; do
    tag_count=$(cnt "$tag")
    if [ "$tag_count" -gt 0 ]; then
        row "Traceability: $tag" "$tag_count occurrences" "PASS"
    else
        row "Traceability: $tag" "0" "FAIL"; fail=1
    fi
done

if [ "$LANG" = "go" ]; then
    scenario_tags="DATA-SCENARIO INFRA-LAYER"
else
    scenario_tags="DATA-SCENARIO IDENTITY-SCENARIO"
fi
for tag in $scenario_tags; do
    tag_count=$(cnt "$tag")
    if [ "$tag_count" -gt 0 ]; then
        row "Traceability: $tag" "$tag_count occurrences" "PASS"
    else
        row "Traceability: $tag" "0" "FAIL"; fail=1
    fi
done

# 3. Float violations in code (not comments)
if [ "$LANG" = "go" ]; then
    float_viol=$(printf '%s' "$code_only" | grep -c '\bfloat64\b' || true)
else
    float_viol=$(printf '%s' "$code_only" | grep -cE '\bfloat\b' || true)
fi
if [ "$float_viol" -gt 0 ]; then
    row "Float type violations (code, not comments)" "$float_viol" "FAIL"; fail=1
else
    row "Float type violations (code, not comments)" "0" "PASS"
fi

# 4. Decimal type usage
if [ "$LANG" = "go" ]; then
    decimal_usage=$(cnt -E 'decimal\.Decimal|shopspring/decimal')
else
    decimal_usage=$(cnt -E 'from decimal import|Decimal\(')
fi
if [ "$decimal_usage" -gt 0 ]; then
    row "Decimal type usage" "$decimal_usage references" "PASS"
else
    row "Decimal type usage" "0 — no Decimal found" "FAIL"; fail=1
fi

# 5. Table-driven / parametrize coverage
if [ "$LANG" = "go" ]; then
    table_count=$(cnt -E '\[\]struct\{|cases :=|testCases :=')
    if [ "$table_count" -gt 0 ]; then
        row "Table-driven test structs" "$table_count" "PASS"
    else
        row "Table-driven test structs" "0" "WARN"; warn=1
    fi
else
    param_count=$(cnt '@pytest.mark.parametrize')
    if [ "$param_count" -gt 0 ]; then
        row "Parametrize decorators" "$param_count" "PASS"
    else
        row "Parametrize decorators" "0" "WARN"; warn=1
    fi
fi

# 6. Boundary condition coverage
boundary_count=$(cnt -iE 'boundary|min|max|negative|zero|null')
if [ "$boundary_count" -ge 5 ]; then
    row "Boundary cases referenced" "$boundary_count" "PASS"
elif [ "$boundary_count" -ge 1 ]; then
    row "Boundary cases referenced" "$boundary_count" "WARN"; warn=1
else
    row "Boundary cases referenced" "0" "FAIL"; fail=1
fi

# 7. Rounding coverage (finance-critical)
if has -iE 'round'; then
    rounding_count=$(cnt -iE 'round')
    row "Rounding coverage" "$rounding_count references" "PASS"
else
    row "Rounding coverage" "0 — no rounding tests" "WARN"; warn=1
fi

echo ""
if [ "$fail" -gt 0 ]; then
    echo "**Overall: FAIL** — finance or traceability violations detected."
    exit 1
elif [ "$warn" -gt 0 ]; then
    echo "**Overall: WARN** — review flagged items."
else
    echo "**Overall: PASS**"
fi
