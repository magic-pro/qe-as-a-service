#!/usr/bin/env bash
# Run the test-creator-agent end-to-end against a target repo and verify output.
# Usage: run-creator-e2e.sh <target-dir>
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:?usage: run-creator-e2e.sh <target-dir>}"
TARGET="$(cd "$TARGET" && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$REPO_ROOT/e2e/runs/$TS"
mkdir -p "$OUT"

echo "== QEaaS test-creator E2E =="
echo "target: $TARGET"
echo "out:    $OUT"

# Preconditions.
command -v claude >/dev/null || { echo "claude CLI not found"; exit 2; }
command -v go >/dev/null     || { echo "go not found"; exit 2; }

# 1. Snapshot pre-run file list.
( cd "$TARGET" && find . -type f -not -path './.git/*' | sort ) > "$OUT/before.list"

# 2. Run the agent headlessly.
PROMPT='Read .qe/data-type-map.md and .qe/identity-map.md in this repo. Examine the existing *_test.go files and helpers/ to learn the table-driven conventions and reuse existing helpers. Generate NEW Go test files (do not modify payment.go or the existing seed test) that cover the required scenarios from the data-type-map: amount-boundary, amount-precision, amount-rounding, currency-unsupported, and cross-border IBAN presence. Every test function must carry the BRD-REQ/JIRA/DATA-SCENARIO/INFRA-LAYER traceability header. Use decimal.Decimal only — never float64. Ensure the package compiles and tests pass.'

echo ">> invoking claude -p --agent test-creator-agent"
( cd "$TARGET" && claude -p --agent test-creator-agent \
    --permission-mode acceptEdits \
    "$PROMPT" ) > "$OUT/run.log" 2>&1
agent_rc=$?
echo "agent exit: $agent_rc"

# 3. Snapshot post-run and diff.
( cd "$TARGET" && find . -type f -not -path './.git/*' | sort ) > "$OUT/after.list"
comm -13 "$OUT/before.list" "$OUT/after.list" | sed 's|^\./||' > "$OUT/newfiles.list"
echo ">> new files:"; cat "$OUT/newfiles.list"

# 4. Structural conformance.
"$REPO_ROOT/e2e/verify-generated.sh" "$TARGET" "$OUT/newfiles.list" | tee "$OUT/verify.txt"
verify_rc=${PIPESTATUS[0]}

# 5. Compile + run.
echo ">> go build ./... && go test ./..."
( cd "$TARGET" && go build ./... && go test ./... ) > "$OUT/gotest.txt" 2>&1
go_rc=$?
tail -n 20 "$OUT/gotest.txt"

# 6. Report.
{
  echo "# E2E Report — $TS"
  echo
  echo "- target: \`$TARGET\`"
  echo "- agent exit: $agent_rc"
  echo "- verify: $([ $verify_rc -eq 0 ] && echo PASS || echo FAIL)"
  echo "- go build+test: $([ $go_rc -eq 0 ] && echo PASS || echo FAIL)"
  echo
  echo "## New files"; echo '```'; cat "$OUT/newfiles.list"; echo '```'
  echo "## Conformance"; echo '```'; cat "$OUT/verify.txt"; echo '```'
  echo "## go test (tail)"; echo '```'; tail -n 20 "$OUT/gotest.txt"; echo '```'
} > "$OUT/report.md"

echo "== report: $OUT/report.md =="
[ $agent_rc -eq 0 ] && [ $verify_rc -eq 0 ] && [ $go_rc -eq 0 ]
