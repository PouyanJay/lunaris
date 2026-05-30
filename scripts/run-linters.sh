#!/usr/bin/env bash
# scripts/run-linters.sh — run Lunaris linters; aggregate exit codes.
#
# Run via: make lint | make lint-fix
#
# Critical rule: never exit on first failure. Run every selected linter,
# aggregate exit codes (bitwise OR), then exit with the aggregate.
#
# Fix mode (--fix) auto-fixes where supported (ruff for Python; prettier +
# eslint for web), then RE-RUNS the check to verify the fix resolved the issue
# (a failing check after --fix means it found something it cannot auto-fix).

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"
ui::init

# --- Argument parsing -------------------------------------------------------

WANT_PYTHON=1
WANT_WEB=1
WANT_SUPABASE=1
FIX_MODE=0

print_help() {
  cat <<EOF
Usage: scripts/run-linters.sh [options]

Run Lunaris linters. Aggregates exit codes across all selected linters.

Options:
  --all              Run all linters (default)
  --python           Run only Python (ruff check + ruff format --check)
  --web              Run only web (TypeScript + ESLint + Prettier)
  --supabase         Run only Supabase (supabase db lint)
  --fix              Auto-fix where supported (ruff, Prettier, ESLint)
                     Compose with scope flags: --python --fix
  -h, --help         Show this help

Behaviour:
  - Check mode (default): ruff check + ruff format --check (non-zero on issues)
  - Fix mode (--fix):     ruff format + ruff check --fix, then re-check
  - Linters whose target is absent (no apps/web, no supabase/migrations) report
    as 'stubbed' and contribute 0 to the aggregate exit code.

Examples:
  scripts/run-linters.sh
  scripts/run-linters.sh --fix
  scripts/run-linters.sh --python --fix
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)  print_help; exit 0 ;;
    --all)      ;;  # explicit "all" is the default
    --python)   WANT_PYTHON=1; WANT_WEB=0; WANT_SUPABASE=0 ;;
    --web)      WANT_PYTHON=0; WANT_WEB=1; WANT_SUPABASE=0 ;;
    --supabase) WANT_PYTHON=0; WANT_WEB=0; WANT_SUPABASE=1 ;;
    --fix)      FIX_MODE=1 ;;
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

# Accumulate exit codes with bitwise OR so a failure in one step is never
# overwritten by a later success — a lint GATE must propagate any failure.
run_ruff_check() {
  local exit_code=0 rc=0
  rc=0; uv run ruff check .          || rc=$?; exit_code=$((exit_code | rc))
  rc=0; uv run ruff format --check . || rc=$?; exit_code=$((exit_code | rc))
  return "$exit_code"
}

run_ruff_fix() {
  local exit_code=0 rc=0
  rc=0; uv run ruff format .         || rc=$?; exit_code=$((exit_code | rc))
  rc=0; uv run ruff check --fix .    || rc=$?; exit_code=$((exit_code | rc))
  # Re-verify (non-zero here = issues ruff could not auto-fix).
  rc=0; uv run ruff check .          || rc=$?; exit_code=$((exit_code | rc))
  rc=0; uv run ruff format --check . || rc=$?; exit_code=$((exit_code | rc))
  return "$exit_code"
}

# --- Banner -----------------------------------------------------------------

if [ "$FIX_MODE" = "1" ]; then
  ui::banner "make lint-fix" "Auto-fixing Lunaris code-quality issues"
else
  ui::banner "make lint" "Running Lunaris code-quality checks"
fi

STEPS=$((WANT_PYTHON + WANT_WEB + WANT_SUPABASE))
[ "$STEPS" -eq 0 ] && ui::die "No linters selected"
CURRENT=0

PYTHON_EXIT=0
WEB_EXIT=0
SB_EXIT=0

# --- Python (ruff) ----------------------------------------------------------

if [ "$WANT_PYTHON" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Python (ruff)"
  if ! command -v uv >/dev/null 2>&1; then
    ui::fail "uv not installed; run 'make setup' first"
    PYTHON_EXIT=1
  elif [ "$FIX_MODE" = "1" ]; then
    run_ruff_fix || PYTHON_EXIT=$?
    if [ "$PYTHON_EXIT" = "0" ]; then
      ui::ok "ruff: formatted + auto-fixed; re-check clean"
    else
      ui::fail "ruff: some issues couldn't be auto-fixed (exit $PYTHON_EXIT)"
    fi
  else
    run_ruff_check || PYTHON_EXIT=$?
    if [ "$PYTHON_EXIT" = "0" ]; then
      ui::ok "ruff check + format-check passed"
    else
      ui::fail "ruff failed (exit $PYTHON_EXIT)"
      ui::hint "Try 'make lint-fix' to auto-fix where possible"
    fi
  fi
fi

# --- Web (TypeScript + ESLint + Prettier) -----------------------------------

if [ "$WANT_WEB" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Web (TypeScript + ESLint + Prettier)"
  if [ ! -f "apps/web/package.json" ]; then
    ui::skip "web: stubbed (apps/web not present)"
  elif ! command -v npm >/dev/null 2>&1; then
    ui::warn "npm not installed — skipping web lint"
    ui::hint "Install Node.js: https://nodejs.org"
  elif [ ! -d "apps/web/node_modules" ]; then
    if [ "$WANT_PYTHON" = "0" ] && [ "$WANT_SUPABASE" = "0" ]; then
      ui::fail "web: deps not installed — run 'cd apps/web && npm install'"
      WEB_EXIT=1
    else
      ui::skip "web: deps not installed (run 'cd apps/web && npm install')"
    fi
  elif [ "$FIX_MODE" = "1" ]; then
    # Fix what's fixable (prettier write + eslint --fix), then re-run the gate.
    ( cd apps/web && npm run format:write && npx eslint . --fix; npm run typecheck && npm run lint && npm run format ) || WEB_EXIT=$?
    if [ "$WEB_EXIT" = "0" ]; then
      ui::ok "web: formatted + auto-fixed; re-check clean"
    else
      ui::fail "web: some issues couldn't be auto-fixed (exit $WEB_EXIT)"
    fi
  else
    ( cd apps/web && npm run typecheck && npm run lint && npm run format ) || WEB_EXIT=$?
    if [ "$WEB_EXIT" = "0" ]; then
      ui::ok "web: typecheck + lint + format passed"
    else
      ui::fail "web lint failed (exit $WEB_EXIT)"
      ui::hint "Try 'make lint-fix' to auto-fix where possible"
    fi
  fi
fi

# --- Supabase (db lint) -----------------------------------------------------

if [ "$WANT_SUPABASE" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "Supabase (supabase db lint)"
  if [ ! -d "supabase/migrations" ]; then
    ui::skip "supabase: stubbed (supabase/migrations not present)"
  elif ! command -v supabase >/dev/null 2>&1; then
    ui::warn "supabase CLI not installed — skipping supabase lint"
    ui::hint "Install: https://supabase.com/docs/guides/cli"
  else
    # `supabase db lint` queries the local database, so it needs the stack up.
    supabase db lint || SB_EXIT=$?
    if [ "$SB_EXIT" = "0" ]; then
      ui::ok "supabase db lint passed"
    else
      ui::fail "supabase db lint failed (exit $SB_EXIT)"
      ui::hint "Is the stack up? Run 'make start' first (db lint needs a live database)"
    fi
  fi
fi

# --- Summary + aggregate exit -----------------------------------------------

TOTAL_EXIT=$((PYTHON_EXIT | WEB_EXIT | SB_EXIT))

ui::summary_begin "Lint Summary"
[ "$WANT_PYTHON" = "1" ]   && ui::summary_row "Python (ruff)" "exit $PYTHON_EXIT" "$(status_for_exit "$PYTHON_EXIT")"
[ "$WANT_WEB" = "1" ]      && ui::summary_row "Web"           "exit $WEB_EXIT"    "$(status_for_exit "$WEB_EXIT")"
[ "$WANT_SUPABASE" = "1" ] && ui::summary_row "Supabase"      "exit $SB_EXIT"     "$(status_for_exit "$SB_EXIT")"
ui::summary_end

if [ "$TOTAL_EXIT" -eq 0 ]; then
  ui::ok "All selected linters passed"
else
  ui::fail "One or more linters failed (aggregate exit $TOTAL_EXIT)"
fi

exit "$TOTAL_EXIT"
