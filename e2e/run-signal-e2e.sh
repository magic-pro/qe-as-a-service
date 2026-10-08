#!/usr/bin/env bash
# Run a synthetic signal through the OKF pipeline and a QEaaS agent, then verify the output.
#   raw payload -> okf normalize -> signal doc -> claude -p --agent <agent> -> OKF finding(s)
#   -> okf validate -> okf expect (expected.yaml)
# Usage: run-signal-e2e.sh <uc1|uc2|uc3|all> [--offline]
#   --offline  stop after normalize + validate (no LLM call)
# Bash 3.2 compatible (macOS default).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$REPO_ROOT/e2e/fixtures/payments-service"
PY="${PYTHON:-python3}"
WHICH="${1:?usage: run-signal-e2e.sh <uc1|uc2|uc3|all> [--offline]}"
OFFLINE=0
[ "${2:-}" = "--offline" ] && OFFLINE=1
TS="$(date +%Y%m%d-%H%M%S)"

COMMON='OFFLINE E2E RUN: no MCP servers are connected and you cannot raise PRs, tickets or fetch URLs. Use only the signal doc and the files in this directory. This directory is the target repo (payments-service); its OKF QE bundle is .qe/ (start at .qe/index.md) and the OKF rules are in okf/conventions.md. Follow your OKF Knowledge Contract exactly. Do not modify any Go source files. When finished, run `python3 -m okf validate .` and fix any errors it reports in files you wrote.'

# Per use case: source, agent, normalize args, task. (No associative arrays in bash 3.2.)
uc_config() {
  case "$1" in
    uc1)
      UC_DIR="uc1-jira-story"; AGENT="planning-agent"
      NORM_ARGS="--source jira --base-url https://synthetic-bank.atlassian.net"
      TASK='Update .qe/data-type-map.md (in place, keeping its frontmatter contract) so it covers every acceptance criterion in the story, append a line to .qe/log.md, and write the Map Update finding to knowledge/findings/PAY-214-map-update.md.' ;;
    uc2)
      UC_DIR="uc2-github-ci"; AGENT="coverage-agent"
      NORM_ARGS="--source github --event workflow_run --log $REPO_ROOT/e2e/signals/uc2-github-ci/gotest.txt"
      TASK='Decide whether the failure is a test bug or an intentional behaviour change (PR #57) that the .qe maps and tests do not reflect. Write the Coverage Gap finding, including a Test Creation Request, to knowledge/findings/payments-service-run-9812345670-coverage-gap.md.' ;;
    uc3)
      UC_DIR="uc3-gcp-logs"; AGENT="incident-agent"
      NORM_ARGS="--source gcp"
      TASK='Write the RCA finding with status awaiting-confirmation to knowledge/findings/0-nq1synthetic7x-incident-rca.md. For this E2E run the harness is the confirming human: after writing the RCA, treat it as confirmed and write the Regression Test Request finding to knowledge/findings/0-nq1synthetic7x-regression-request.md.' ;;
    *) echo "unknown use case: $1" >&2; return 1 ;;
  esac
}

run_uc() {
  local uc="$1"
  uc_config "$uc" || return 2
  local sig="$REPO_ROOT/e2e/signals/$UC_DIR"
  local out="$REPO_ROOT/e2e/runs/$TS-$uc"
  local ws="$out/workspace"
  mkdir -p "$out"
  echo "== QEaaS signal E2E: $uc ($UC_DIR -> $AGENT) =="
  echo "out: $out"

  # 1. Workspace = copy of the fixture + OKF tooling + the strategic agent + empty knowledge bundle.
  cp -R "$FIXTURE" "$ws"
  cp -R "$REPO_ROOT/okf" "$ws/okf"
  rm -rf "$ws/okf/tests" "$ws/okf/__pycache__"
  cp "$REPO_ROOT/.claude/agents/$AGENT.md" "$ws/.claude/agents/"
  mkdir -p "$ws/knowledge/signals/jira" "$ws/knowledge/signals/github" "$ws/knowledge/signals/gcp" "$ws/knowledge/findings"
  cp "$REPO_ROOT/knowledge/signals/index.md" "$ws/knowledge/signals/index.md"
  cp "$REPO_ROOT/knowledge/findings/index.md" "$ws/knowledge/findings/index.md"
  cat > "$ws/.claude/settings.json" <<'JSON'
{
  "permissions": {
    "allow": ["Read", "Write", "Edit", "Glob", "Grep",
              "Bash(ls:*)", "Bash(cat:*)", "Bash(go build:*)", "Bash(go test:*)", "Bash(go vet:*)",
              "Bash(python3 -m okf:*)"]
  }
}
JSON

  # 2. Normalize the raw synthetic payload into an OKF signal doc.
  # shellcheck disable=SC2086
  local doc
  doc="$(cd "$ws" && "$PY" -m okf normalize $NORM_ARGS "$sig/raw.json" --out knowledge/signals)"
  local norm_rc=$?
  doc="${doc#$ws/}"
  echo "signal doc: $doc"

  # 3. Validate the signal bundle before any agent sees it.
  ( cd "$ws" && "$PY" -m okf validate knowledge/signals ) > "$out/validate-signal.txt" 2>&1
  local sigval_rc=$?
  tail -n 1 "$out/validate-signal.txt"

  local agent_rc=-1 val_rc=-1 exp_rc=-1
  if [ "$OFFLINE" -eq 0 ] && [ $norm_rc -eq 0 ] && [ $sigval_rc -eq 0 ]; then
    command -v claude >/dev/null || { echo "claude CLI not found"; return 2; }
    # 4. Run the agent headlessly with the signal doc as its input contract.
    echo ">> invoking claude -p --agent $AGENT"
    ( cd "$ws" && claude -p --agent "$AGENT" --permission-mode acceptEdits \
        "Signal doc: $doc

$COMMON

$TASK" ) > "$out/run.log" 2>&1
    agent_rc=$?
    echo "agent exit: $agent_rc"

    # 5. Validate everything the agent wrote, then assert expected.yaml.
    ( cd "$ws" && "$PY" -m okf validate . ) > "$out/validate.txt" 2>&1
    val_rc=$?
    tail -n 1 "$out/validate.txt"
    ( cd "$ws" && "$PY" -m okf expect "$sig/expected.yaml" . ) > "$out/expect.txt" 2>&1
    exp_rc=$?
    cat "$out/expect.txt"
  fi

  status() { if [ "$1" -eq 0 ]; then echo PASS; elif [ "$1" -lt 0 ]; then echo SKIPPED; else echo FAIL; fi; }
  {
    echo "# Signal E2E Report — $uc ($TS)"
    echo
    echo "- use case: \`$UC_DIR\` → \`$AGENT\`"
    echo "- signal doc: \`$doc\`"
    echo "- normalize: $(status $norm_rc)"
    echo "- signal validate: $(status $sigval_rc)"
    echo "- agent exit: $agent_rc"
    echo "- bundle validate: $(status $val_rc)"
    echo "- expected outputs: $(status $exp_rc)"
    echo
    echo "## Signal validation"; echo '```'; cat "$out/validate-signal.txt"; echo '```'
    if [ -f "$out/validate.txt" ]; then
      echo "## Bundle validation"; echo '```'; cat "$out/validate.txt"; echo '```'
      echo "## Expected outputs"; echo '```'; cat "$out/expect.txt"; echo '```'
      echo "## Agent output (tail)"; echo '```'; tail -n 30 "$out/run.log"; echo '```'
    fi
  } > "$out/report.md"
  echo "== report: $out/report.md =="

  [ $norm_rc -eq 0 ] && [ $sigval_rc -eq 0 ] || return 1
  [ "$OFFLINE" -eq 1 ] && return 0
  [ $agent_rc -eq 0 ] && [ $val_rc -eq 0 ] && [ $exp_rc -eq 0 ]
}

if [ "$WHICH" = "all" ]; then
  rc=0
  for uc in uc1 uc2 uc3; do run_uc "$uc" || rc=1; echo; done
  exit $rc
fi
run_uc "$WHICH"
