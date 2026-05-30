#!/usr/bin/env bash
# scripts/run-tests.sh — run Lunaris test suites; aggregate exit codes.
#
# Run via: make test | make test-python | make test-web | make test-eval
#
# Critical rule: never exit on first failure. Run every selected suite,
# aggregate exit codes (bitwise OR), then exit with the aggregate — the
# developer needs to see EVERY failure, not just the first one.
#
# Suites:
#   python  — the deterministic pytest suite (live evals auto-excluded via the
#             pyproject `-m "not eval"` default). No API key needed.
#   web     — the apps/web Vitest suite.
#   eval    — the LIVE LLM evals (pytest -m eval). Opt-in: needs ANTHROPIC_API_KEY
#             in .env, makes real Claude calls, and is rate-limited. NOT in --all.
#
# Pytest exit codes treated as success: 0 (passed) and 5 (no tests collected).

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"
ui::init

# --- Argument parsing -------------------------------------------------------

WANT_PYTHON=1
WANT_WEB=1
WANT_EVAL=0   # opt-in only — never part of --all

print_help() {
  cat <<EOF
Usage: scripts/run-tests.sh [options]

Run Lunaris test suites. Aggregates exit codes across all selected suites.

Options:
  --all              Run the standard suites: python + web (default)
  --python           Run only the deterministic Python suite (pytest)
  --web              Run only the web suite (Vitest)
  --eval             Run only the LIVE LLM evals (pytest -m eval)
                     Opt-in: needs ANTHROPIC_API_KEY in .env; real Claude calls.
  -h, --help         Show this help

Behaviour:
  - Suites with no tests collected (pytest exit 5) report as 'none yet'.
  - Suites whose target is absent (no apps/web) report as 'stubbed' and
    contribute 0 to the aggregate exit code.
  - Real failures always contribute non-zero.

Examples:
  scripts/run-tests.sh            # python + web
  scripts/run-tests.sh --python
  scripts/run-tests.sh --eval     # live Claude evals (slow, rate-limited)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) print_help; exit 0 ;;
    --all)     WANT_PYTHON=1; WANT_WEB=1; WANT_EVAL=0 ;;
    --python)  WANT_PYTHON=1; WANT_WEB=0; WANT_EVAL=0 ;;
    --web)     WANT_PYTHON=0; WANT_WEB=1; WANT_EVAL=0 ;;
    --eval)    WANT_PYTHON=0; WANT_WEB=0; WANT_EVAL=1 ;;
    *)
      printf "ERROR: unknown argument: %s\n" "$1" >&2
      printf "Run with --help for usage.\n" >&2
      exit 2
      ;;
  esac
  shift
done

# --- Helpers ----------------------------------------------------------------

status_for_exit() { [ "$1" = "0" ] && echo "ok" || echo "fail"; }

# Run a pytest invocation, treating exit 5 (no tests collected) as success.
# Lets pytest output flow to the terminal so failures are visible inline.
run_pytest() {
  local label="$1"; shift
  local exit_code=0
  uv run "$@" || exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    ui::ok "${label}: passed"; return 0
  fi
  if [ "$exit_code" -eq 5 ]; then
    ui::skip "${label}: no tests collected"; return 0
  fi
  ui::fail "${label} failed (pytest exit $exit_code)"
  return "$exit_code"
}

# --- Banner -----------------------------------------------------------------

ui::banner "make test" "Running Lunaris test suites"

STEPS=$((WANT_PYTHON + WANT_WEB + WANT_EVAL))
[ "$STEPS" -eq 0 ] && ui::die "No suites selected" "Pass --python, --web, --eval, or --all"
CURRENT=0

PYTHON_EXIT=0
WEB_EXIT=0
EVAL_EXIT=0

# --- Python (deterministic) -------------------------------------------------

if [ "$WANT_PYTHON" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Python (pytest — deterministic, evals excluded)"
  if ! command -v uv >/dev/null 2>&1; then
    ui::fail "uv not installed; run 'make setup' first"
    PYTHON_EXIT=1
  else
    run_pytest "python" pytest -q || PYTHON_EXIT=$?
  fi
fi

# --- Web (Vitest) -----------------------------------------------------------

if [ "$WANT_WEB" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Web (Vitest)"
  if [ ! -f "apps/web/package.json" ]; then
    ui::skip "web: stubbed (apps/web not present)"
  elif ! command -v npm >/dev/null 2>&1; then
    ui::warn "npm not installed — skipping web tests"
    ui::hint "Install Node.js: https://nodejs.org"
  elif [ ! -d "apps/web/node_modules" ]; then
    # Vitest needs installed deps. When web is the ONLY requested scope, the
    # caller wants it — fail loudly. Otherwise (the all-surface `make test`)
    # skip so it stays green; CI's web job runs `npm ci` first.
    if [ "$WANT_PYTHON" = "0" ] && [ "$WANT_EVAL" = "0" ]; then
      ui::fail "web: deps not installed — run 'cd apps/web && npm install'"
      WEB_EXIT=1
    else
      ui::skip "web: deps not installed (run 'cd apps/web && npm install')"
    fi
  else
    ( cd apps/web && npm test ) || WEB_EXIT=$?
    [ "$WEB_EXIT" = "0" ] && ui::ok "web: passed" || ui::fail "web failed (vitest exit $WEB_EXIT)"
  fi
fi

# --- Eval (live Claude) -----------------------------------------------------

if [ "$WANT_EVAL" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Live evals (pytest -m eval — real Claude calls)"
  if ! command -v uv >/dev/null 2>&1; then
    ui::fail "uv not installed; run 'make setup' first"
    EVAL_EXIT=1
  elif [ ! -f ".env" ]; then
    ui::warn "no .env — live evals need ANTHROPIC_API_KEY"
    ui::hint "cp .env.sample .env && edit it, then re-run 'make test-eval'"
  else
    ui::info "live evals make real Claude calls and are rate-limited (~50 req/min)"
    run_pytest "eval" --env-file .env pytest -m eval -q || EVAL_EXIT=$?
  fi
fi

# --- Summary + aggregate exit -----------------------------------------------

TOTAL_EXIT=$((PYTHON_EXIT | WEB_EXIT | EVAL_EXIT))

ui::summary_begin "Test Summary"
[ "$WANT_PYTHON" = "1" ] && ui::summary_row "Python" "exit $PYTHON_EXIT" "$(status_for_exit "$PYTHON_EXIT")"
[ "$WANT_WEB" = "1" ]    && ui::summary_row "Web"    "exit $WEB_EXIT"    "$(status_for_exit "$WEB_EXIT")"
[ "$WANT_EVAL" = "1" ]   && ui::summary_row "Eval"   "exit $EVAL_EXIT"   "$(status_for_exit "$EVAL_EXIT")"
ui::summary_end

if [ "$TOTAL_EXIT" -eq 0 ]; then
  ui::ok "All selected suites passed"
else
  ui::fail "One or more suites failed (aggregate exit $TOTAL_EXIT)"
fi

exit "$TOTAL_EXIT"
