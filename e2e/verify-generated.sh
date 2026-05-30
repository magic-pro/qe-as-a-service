#!/usr/bin/env bash
# Structural conformance checks for agent-generated Go test files.
# Usage: verify-generated.sh <target-dir> <newfiles-list-file>
# Exits non-zero on any violation. Prints a check table.
# Bash 3.2 compatible (macOS default).
set -uo pipefail

TARGET="$1"
NEWFILES="$2"   # file containing newline-separated paths of newly created files
fail=0

note() { printf '  %-40s %s\n' "$1" "$2"; }

# Newline-separated list of new *_test.go files (may be empty).
test_files="$(grep -E '_test\.go$' "$NEWFILES" 2>/dev/null || true)"
count="$(printf '%s' "$test_files" | grep -c . || true)"

if [ "$count" -eq 0 ]; then
  note "new *_test.go files created" "FAIL (none)"
  echo "RESULT: FAIL"
  exit 1
fi
note "new *_test.go files created" "PASS ($count)"

# Concatenate the contents of every new test file ONCE into a variable.
# (Reading into a var avoids `cat | grep -q` SIGPIPE interacting with pipefail,
#  which otherwise misreports matches as failures on larger inputs.)
content=""
while IFS= read -r f; do
  [ -n "$f" ] && content="$content$(cat "$TARGET/$f")
"
done <<EOF
$test_files
EOF

# has <pattern> [-i] : grep the captured content, immune to pipefail/SIGPIPE.
has() { printf '%s' "$content" | grep -q "$@"; }

# Code-only view: drop // line comments so prose mentioning a banned token
# (e.g. "never use float64") does not trip the check.
code_only="$(printf '%s' "$content" | sed 's://.*$::')"
has_code() { printf '%s' "$code_only" | grep -q "$@"; }

# 1. Traceability headers present.
for tag in "BRD-REQ" "JIRA" "DATA-SCENARIO" "INFRA-LAYER"; do
  if has "$tag"; then note "traceability: $tag" "PASS"; else note "traceability: $tag" "FAIL"; fail=1; fi
done

# 2. No float64 for money (in actual code, not comments).
if has_code "float64"; then note "no float64 in money tests" "FAIL"; fail=1; else note "no float64 in money tests" "PASS"; fi

# 3. decimal used.
if has "shopspring/decimal"; then note "uses decimal.Decimal" "PASS"; else note "uses decimal.Decimal" "FAIL"; fail=1; fi

# 4. Reuses existing helpers package (not duplicated).
if has "payments-service/helpers"; then note "reuses helpers package" "PASS"; else note "reuses helpers package" "WARN"; fi

# 5. Boundary + rounding scenarios.
if has -iE "boundary|min|max|negative|zero"; then note "amount-boundary coverage" "PASS"; else note "amount-boundary coverage" "FAIL"; fail=1; fi
if has -iE "round"; then note "amount-rounding coverage" "PASS"; else note "amount-rounding coverage" "FAIL"; fail=1; fi

if [ "$fail" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
