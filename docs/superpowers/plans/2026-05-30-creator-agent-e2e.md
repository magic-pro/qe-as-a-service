---
type: Implementation Plan
title: Test-Creator Agent Local E2E Proof Harness — Implementation Plan
description: Task-by-task plan implementing the test-creator E2E harness (fixture, runner, conformance checker).
timestamp: 2026-05-30T00:00:00Z
derived_from: ../specs/2026-05-30-creator-agent-e2e-design.md
tags: [e2e, test-creator-agent, plan]
---

# Test-Creator Agent Local E2E Proof Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the QEaaS `test-creator-agent` runs end-to-end locally by scaffolding a real finance Go microservice fixture, invoking the agent headlessly via `claude -p --agent test-creator-agent`, and verifying the generated tests compile, pass, and meet finance constraints.

**Architecture:** A self-contained, compilable Go microservice fixture (`e2e/fixtures/payments-service/`) carries genuine validation logic, `.qe/` maps, a seed test, and the copied agent definition. A repo-agnostic runner (`e2e/run-creator-e2e.sh <target-dir>`) snapshots files, runs the agent, diffs the result, runs structural conformance checks (`verify-generated.sh`), then `go build && go test`, and writes a report.

**Tech Stack:** Go 1.22 (shopspring/decimal, testify, google/uuid), `claude` CLI 2.1.x headless mode, bash.

---

## File Structure

- Create: `e2e/fixtures/payments-service/go.mod` — module def
- Create: `e2e/fixtures/payments-service/payments/payment.go` — real validation logic
- Create: `e2e/fixtures/payments-service/payments/payment_test.go` — seed table-driven test
- Create: `e2e/fixtures/payments-service/helpers/synthetic_data.go` — finance-safe generators (reused by agent)
- Create: `e2e/fixtures/payments-service/.qe/data-type-map.md` — transaction-scoped map
- Create: `e2e/fixtures/payments-service/.qe/identity-map.md` — auth-boundary slice
- Create: `e2e/fixtures/payments-service/.claude/agents/test-creator-agent.md` — copied from repo-templates
- Create: `e2e/fixtures/payments-service/.claude/settings.json` — permissions for headless run
- Create: `e2e/verify-generated.sh` — structural conformance checks
- Create: `e2e/run-creator-e2e.sh` — orchestrator
- Modify: `.gitignore` — ignore `e2e/runs/`

---

## Task 1: Install and verify the Go toolchain

**Files:** none (environment setup)

- [ ] **Step 1: Check whether Go is already present**

Run: `go version 2>&1 || echo "GO_MISSING"`
Expected: either a version line, or `GO_MISSING`.

- [ ] **Step 2: Install Go if missing**

Run: `brew install go`
Expected: Homebrew installs go; exit 0. (If brew is unavailable, fall back to the official pkg from go.dev — but brew is present on this machine.)

- [ ] **Step 3: Verify the toolchain**

Run: `go version && go env GOPATH`
Expected: `go version go1.2x ...` and a GOPATH line, exit 0.

---

## Task 2: Scaffold the Go module and finance-safe helpers

**Files:**
- Create: `e2e/fixtures/payments-service/go.mod`
- Create: `e2e/fixtures/payments-service/helpers/synthetic_data.go`

- [ ] **Step 1: Create the go.mod**

`e2e/fixtures/payments-service/go.mod`:

```
module payments-service

go 1.22

require (
	github.com/shopspring/decimal v1.4.0
	github.com/stretchr/testify v1.9.0
	github.com/google/uuid v1.6.0
)
```

- [ ] **Step 2: Create finance-safe synthetic generators**

`e2e/fixtures/payments-service/helpers/synthetic_data.go`:

```go
// Package helpers provides finance-safe synthetic data generators.
// Never use real PII. All monetary values use decimal.Decimal, never float64.
package helpers

import (
	"fmt"
	"math/rand"
	"strings"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
)

var currencyDecimals = map[string]int32{
	"GBP": 2, "USD": 2, "EUR": 2, "JPY": 0, "BHD": 3,
}

// SyntheticAmount returns a random Decimal within range, respecting currency precision.
func SyntheticAmount(minStr, maxStr, currency string) decimal.Decimal {
	dp, ok := currencyDecimals[currency]
	if !ok {
		dp = 2
	}
	lo, _ := decimal.NewFromString(minStr)
	hi, _ := decimal.NewFromString(maxStr)
	diff := hi.Sub(lo)
	frac := decimal.NewFromFloat(rand.Float64()) //nolint:gosec
	return lo.Add(diff.Mul(frac)).RoundBank(dp)
}

// SyntheticCurrencyCode returns a random valid ISO 4217 currency code.
func SyntheticCurrencyCode() string {
	codes := []string{"GBP", "USD", "EUR", "JPY", "BHD"}
	return codes[rand.Intn(len(codes))] //nolint:gosec
}

// SyntheticIBAN returns a plausible IBAN format string (not checksum-valid).
func SyntheticIBAN(country string) string {
	lengths := map[string]int{"GB": 22, "DE": 22, "FR": 27, "NL": 18}
	length, ok := lengths[country]
	if !ok {
		length = 22
	}
	chars := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	b := make([]byte, length-2)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))] //nolint:gosec
	}
	return country + string(b)
}

// SyntheticName returns a non-real full name.
func SyntheticName() string {
	firsts := []string{"Alex", "Jordan", "Morgan", "Taylor", "Casey"}
	lasts := []string{"Smith", "Jones", "Williams", "Brown", "Davies"}
	return firsts[rand.Intn(len(firsts))] + " " + lasts[rand.Intn(len(lasts))] //nolint:gosec
}

// SyntheticEmail returns a non-real, format-valid email using the @qe.invalid domain.
func SyntheticEmail(name string) string {
	local := strings.ToLower(strings.ReplaceAll(name, " ", "."))
	return fmt.Sprintf("%s.%s@qe.invalid", local, uuid.New().String()[:4])
}

// SyntheticTransactionID returns a UUID v4 string.
func SyntheticTransactionID() string { return uuid.New().String() }

// SyntheticCorrelationID returns a UUID v4 string.
func SyntheticCorrelationID() string { return uuid.New().String() }
```

- [ ] **Step 3: Commit (deps resolved later with source)**

```bash
git add e2e/fixtures/payments-service/go.mod e2e/fixtures/payments-service/helpers/synthetic_data.go
git commit -m "feat(e2e): scaffold payments-service module + finance-safe helpers"
```

---

## Task 3: Implement the service-under-test with real validation logic

**Files:**
- Create: `e2e/fixtures/payments-service/payments/payment.go`

- [ ] **Step 1: Write the payment validation logic**

`e2e/fixtures/payments-service/payments/payment.go`:

```go
// Package payments validates and processes financial payments.
// Monetary values are always decimal.Decimal — never float64.
package payments

import (
	"errors"

	"github.com/shopspring/decimal"
)

// currencyDecimals maps ISO 4217 codes to their permitted decimal places.
var currencyDecimals = map[string]int32{
	"GBP": 2, "USD": 2, "EUR": 2, "JPY": 0, "BHD": 3,
}

// maxAmount is the largest payment the platform accepts.
const maxAmount = "999999999.99"

// Sentinel errors. Error strings double as machine error codes.
var (
	ErrInvalidAmount      = errors.New("INVALID_AMOUNT")
	ErrUnsupportedCurrency = errors.New("UNSUPPORTED_CURRENCY")
	ErrPrecisionExceeded  = errors.New("PRECISION_EXCEEDED")
	ErrMissingIBAN        = errors.New("MISSING_IBAN")
)

// Payment is a single payment instruction.
type Payment struct {
	Amount      decimal.Decimal
	Currency    string
	CrossBorder bool
	IBAN        string
}

// ValidateAmount checks an amount against currency rules.
// Returns nil when valid, or a sentinel error code.
func ValidateAmount(amount decimal.Decimal, currency string) error {
	dp, ok := currencyDecimals[currency]
	if !ok {
		return ErrUnsupportedCurrency
	}
	if amount.Sign() <= 0 {
		return ErrInvalidAmount
	}
	max, _ := decimal.NewFromString(maxAmount)
	if amount.GreaterThan(max) {
		return ErrInvalidAmount
	}
	// Exponent is negative for fractional places; -3 means 3 dp.
	if amount.Exponent() < -dp {
		return ErrPrecisionExceeded
	}
	return nil
}

// ProcessPayment validates a payment and enforces cross-border rules.
func ProcessPayment(p Payment) error {
	if err := ValidateAmount(p.Amount, p.Currency); err != nil {
		return err
	}
	if p.CrossBorder && p.IBAN == "" {
		return ErrMissingIBAN
	}
	return nil
}
```

- [ ] **Step 2: Commit**

```bash
git add e2e/fixtures/payments-service/payments/payment.go
git commit -m "feat(e2e): payments-service validation logic (decimal-only)"
```

---

## Task 4: Add the seed test and prove the module compiles + passes

**Files:**
- Create: `e2e/fixtures/payments-service/payments/payment_test.go`

- [ ] **Step 1: Write the seed table-driven test (establishes conventions the agent will mimic)**

`e2e/fixtures/payments-service/payments/payment_test.go`:

```go
package payments_test

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

func TestValidateAmount_GBPBoundaries(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-boundary
	// INFRA-LAYER: API

	cases := []struct {
		name    string
		amount  string
		wantErr error
	}{
		{"min positive GBP", "0.01", nil},
		{"zero", "0", payments.ErrInvalidAmount},
		{"negative", "-1.00", payments.ErrInvalidAmount},
		{"max valid", "999999999.99", nil},
		{"too many places", "0.001", payments.ErrPrecisionExceeded},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			amt, _ := decimal.NewFromString(tc.amount)
			err := payments.ValidateAmount(amt, "GBP")
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
```

- [ ] **Step 2: Resolve dependencies**

Run: `cd e2e/fixtures/payments-service && go mod tidy`
Expected: `go.sum` created, deps downloaded, exit 0. (Requires network for the module proxy.)

- [ ] **Step 3: Run the seed test to verify the fixture is green BEFORE the agent runs**

Run: `cd e2e/fixtures/payments-service && go test ./...`
Expected: `ok  payments-service/payments` — PASS, exit 0.

- [ ] **Step 4: Commit**

```bash
git add e2e/fixtures/payments-service/payments/payment_test.go e2e/fixtures/payments-service/go.sum
git commit -m "test(e2e): seed table-driven test; fixture compiles and passes"
```

---

## Task 5: Author the `.qe/` maps for the fixture

**Files:**
- Create: `e2e/fixtures/payments-service/.qe/data-type-map.md`
- Create: `e2e/fixtures/payments-service/.qe/identity-map.md`

- [ ] **Step 1: Write the transaction-scoped data-type map**

`e2e/fixtures/payments-service/.qe/data-type-map.md`:

```markdown
# Data Type Map — payments-service (Transaction-Scoped)

**Scope:** Payment instruction fields handled by `payments.ProcessPayment`.
**BRD Reference:** BRD-PAY-001
**Jira Story:** STORY-789

## Fields

| Field | Type | Constraints | Boundary scenarios to test |
|---|---|---|---|
| amount | decimal.Decimal | > 0, <= 999999999.99, currency-precision | null/zero, min (0.01), max (999999999.99), negative, precision-exceeded (0.001 GBP), rounding boundary (0.005 GBP -> 0.01) |
| currency | string (ISO 4217) | one of GBP,USD,EUR,JPY,BHD | supported, unsupported (ZZZ), empty, JPY 0dp, BHD 3dp |
| cross_border | bool | — | true+missing IBAN, true+present IBAN, false |
| iban | string | required when cross_border | present, empty when cross-border, malformed |

## Decimal precision rules

| Currency | Decimal places | Example valid | Example invalid |
|---|---|---|---|
| GBP/USD/EUR | 2 | 12.34 | 12.345 |
| JPY | 0 | 100 | 100.5 |
| BHD | 3 | 1.234 | 1.2345 |

## Required scenarios (must all be covered)

- amount-boundary (null/zero/min/max/negative)
- amount-precision (per-currency decimal places)
- amount-rounding (half-up / bankers rounding at the boundary)
- currency-unsupported
- cross-border IBAN presence
```

- [ ] **Step 2: Write the auth-boundary identity slice**

`e2e/fixtures/payments-service/.qe/identity-map.md`:

```markdown
# Identity Map — payments-service (Auth Boundary Slice)

**Scope:** Auth boundary relevant to the payments service layer.
**BRD Reference:** BRD-PAY-001
**Jira Story:** STORY-789

## Token Validation at API Layer

| Scenario | Input | Expected |
|---|---|---|
| Valid JWT, valid scope | Bearer token, correct audience + scope | request processed |
| Expired JWT | token past exp | 401 |
| Missing token | no Authorization header | 401 |
| Wrong scope for POST /payments | token without payments:write | 403 |

## Correlation ID Propagation

| Scenario | Expected |
|---|---|
| X-Correlation-ID present | propagated to downstream + audit log |
| X-Correlation-ID absent | new UUID generated and propagated |

> Note: the service-under-test in this fixture exposes pure validation functions,
> so auth scenarios are documented for traceability; the agent should focus test
> generation on the data-type-map scenarios that map to callable code.
```

- [ ] **Step 3: Commit**

```bash
git add e2e/fixtures/payments-service/.qe/
git commit -m "docs(e2e): qe maps for payments-service fixture"
```

---

## Task 6: Install the agent definition and headless settings into the fixture

**Files:**
- Create: `e2e/fixtures/payments-service/.claude/agents/test-creator-agent.md`
- Create: `e2e/fixtures/payments-service/.claude/settings.json`

- [ ] **Step 1: Copy the real agent definition (do not hand-edit — it must be the shipped one)**

Run:
```bash
mkdir -p e2e/fixtures/payments-service/.claude/agents
cp repo-templates/microservices-repo/.claude/agents/test-creator-agent.md \
   e2e/fixtures/payments-service/.claude/agents/test-creator-agent.md
```
Expected: file copied, exit 0.

- [ ] **Step 2: Add settings to allow the headless run to edit/test without prompts**

`e2e/fixtures/payments-service/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Bash(go build:*)",
      "Bash(go test:*)",
      "Bash(go vet:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Glob",
      "Grep"
    ]
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add e2e/fixtures/payments-service/.claude/
git commit -m "chore(e2e): install test-creator-agent + headless settings in fixture"
```

---

## Task 7: Write the structural conformance checker

**Files:**
- Create: `e2e/verify-generated.sh`

- [ ] **Step 1: Write verify-generated.sh**

`e2e/verify-generated.sh`:

```bash
#!/usr/bin/env bash
# Structural conformance checks for agent-generated Go test files.
# Usage: verify-generated.sh <target-dir> <newfiles-list-file>
# Exits non-zero on any violation. Prints a check table.
set -uo pipefail

TARGET="$1"
NEWFILES="$2"   # file containing newline-separated paths of newly created files
fail=0

note() { printf '  %-40s %s\n' "$1" "$2"; }

# Collect new *_test.go files only.
mapfile -t test_files < <(grep -E '_test\.go$' "$NEWFILES" || true)

if [ "${#test_files[@]}" -eq 0 ]; then
  note "new *_test.go files created" "FAIL (none)"
  echo "RESULT: FAIL"
  exit 1
fi
note "new *_test.go files created" "PASS (${#test_files[@]})"

joined=$(printf '%s\n' "${test_files[@]}")
catall() { while read -r f; do [ -n "$f" ] && cat "$TARGET/$f"; done <<<"$joined"; }

# 1. Traceability headers present.
for tag in "BRD-REQ" "JIRA" "DATA-SCENARIO" "INFRA-LAYER"; do
  if catall | grep -q "$tag"; then note "traceability: $tag" "PASS"; else note "traceability: $tag" "FAIL"; fail=1; fi
done

# 2. No float64 for money (no float64 anywhere in generated tests).
if catall | grep -q "float64"; then note "no float64 in money tests" "FAIL"; fail=1; else note "no float64 in money tests" "PASS"; fi

# 3. decimal used.
if catall | grep -q "shopspring/decimal"; then note "uses decimal.Decimal" "PASS"; else note "uses decimal.Decimal" "FAIL"; fail=1; fi

# 4. Reuses existing helpers package (not duplicated).
if catall | grep -q "payments-service/helpers"; then note "reuses helpers package" "PASS"; else note "reuses helpers package" "WARN"; fi

# 5. Boundary + rounding scenarios.
if catall | grep -qiE "boundary|min|max|negative|zero"; then note "amount-boundary coverage" "PASS"; else note "amount-boundary coverage" "FAIL"; fail=1; fi
if catall | grep -qiE "round"; then note "amount-rounding coverage" "PASS"; else note "amount-rounding coverage" "FAIL"; fail=1; fi

if [ "$fail" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
```

- [ ] **Step 2: Make it executable and smoke-test the negative path**

Run:
```bash
chmod +x e2e/verify-generated.sh
printf '' > /tmp/empty.list
e2e/verify-generated.sh e2e/fixtures/payments-service /tmp/empty.list; echo "exit=$?"
```
Expected: prints `new *_test.go files created  FAIL (none)`, `RESULT: FAIL`, `exit=1`.

- [ ] **Step 3: Commit**

```bash
git add e2e/verify-generated.sh
git commit -m "feat(e2e): structural conformance checker for generated tests"
```

---

## Task 8: Write the orchestrator runner

**Files:**
- Create: `e2e/run-creator-e2e.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Add runs/ to .gitignore**

Append to `.gitignore`:

```
# QEaaS E2E run artifacts
e2e/runs/
```

- [ ] **Step 2: Write run-creator-e2e.sh**

`e2e/run-creator-e2e.sh`:

```bash
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
```

- [ ] **Step 3: Make executable and commit**

```bash
chmod +x e2e/run-creator-e2e.sh
git add e2e/run-creator-e2e.sh .gitignore
git commit -m "feat(e2e): orchestrator runner for test-creator E2E"
```

---

## Task 9: Execute the end-to-end run and evaluate

**Files:** none (produces `e2e/runs/<ts>/` artifacts, gitignored)

- [ ] **Step 1: Run the harness against the fixture**

Run: `e2e/run-creator-e2e.sh e2e/fixtures/payments-service`
Expected: agent runs, new `*_test.go` files appear, conformance `RESULT: PASS`, `go test` `ok`. Final exit 0.

- [ ] **Step 2: Inspect the report**

Run: `cat e2e/runs/*/report.md | tail -n 60`
Expected: agent exit 0, verify PASS, go build+test PASS, and a list of generated test files.

- [ ] **Step 3: Evaluate against the 7 success criteria (manual)**

Confirm from the report + generated files: (1) agent exit 0; (2) ≥1 new test file; (3) traceability headers; (4) no float64; (5) helper reuse; (6) boundary + rounding scenarios; (7) go test green. Note any criterion not met as a real finding (agent gap, not harness bug).

- [ ] **Step 4: Commit the generated tests as proof artifact (optional, reviewed)**

```bash
git add e2e/fixtures/payments-service/payments/
git commit -m "test(e2e): agent-generated tests from E2E proof run"
```

---

## Self-Review

**Spec coverage:**
- Fixture (source + helpers + seed test + maps + agent def): Tasks 2–6. ✓
- Real headless invocation: Task 8 (`claude -p --agent test-creator-agent`). ✓
- Install Go + run for real: Tasks 1, 4, 9. ✓
- Structural conformance (7 criteria): Task 7 + Task 9 Step 3. ✓
- Repo-agnostic runner (target-dir arg): Task 8. ✓ (`--stack` flag deferred; Phase 2 adds pytest branch — out of scope this plan.)
- Output to `runs/<ts>/`, gitignored: Task 8. ✓
- Phase 2 (pytest+devcontainer, mono): explicitly out of scope. ✓

**Placeholder scan:** No TBD/TODO; all code and commands are concrete.

**Type consistency:** `ValidateAmount(decimal.Decimal, string) error`, `ProcessPayment(Payment) error`, sentinel errors `ErrInvalidAmount/ErrUnsupportedCurrency/ErrPrecisionExceeded/ErrMissingIBAN`, module path `payments-service`, helpers import `payments-service/helpers` — consistent across Tasks 2, 3, 4, 7, 8.

**Known risk:** `go mod tidy` and the agent's own `go test` need network for the module proxy. If offline, Task 4 Step 2 fails fast with a clear error — surface it rather than working around.
