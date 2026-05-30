#!/usr/bin/env bash
# scripts/install.sh — idempotent Lunaris developer environment setup.
#
# Run via: make setup
#
# Hard prerequisites (abort if missing): bash, git, curl
# Bootstraps:  uv (via curl) if missing
# Installs:    Python workspace deps (uv sync --all-packages); web deps (npm)
# Configures:  .env from .env.sample (if .env missing)
# Soft prereqs (warn but never fail): docker, supabase CLI, node
#
# Every step is idempotent — re-running is safe and skips what's already done.

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"
ui::init

# --- Argument parsing --------------------------------------------------------

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      cat <<EOF
Usage: scripts/install.sh [options]

Sets up the Lunaris developer environment. Idempotent — safe to re-run.

Options:
  -h, --help     Show this help

Hard prerequisites (aborts if missing):
  bash, git, curl

What this installs:
  - uv (Python package manager) — bootstrapped via curl if missing
  - Python workspace dependencies via 'uv sync --all-packages'
  - Web dependencies (apps/web) via 'npm install' (if node present)
  - .env from .env.sample (if .env doesn't yet exist)

Soft prerequisites (warns but never fails):
  - docker    (needed by 'make start' — the local Supabase stack runs in it)
  - supabase  (the local Postgres + pgvector data layer CLI)
  - node      (needed by apps/web)

Examples:
  scripts/install.sh             # full setup
  NO_COLOR=1 scripts/install.sh  # plain output (CI-safe)
EOF
      exit 0
      ;;
    *)
      printf "ERROR: unknown argument: %s\n" "$arg" >&2
      printf "Run with --help for usage.\n" >&2
      exit 2
      ;;
  esac
done

# --- Counters & helpers ------------------------------------------------------

INSTALLED=0
SKIPPED=0
WARNED=0

check_hard_prereq() {
  local cmd="$1"
  local hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    ui::ok "$cmd"
    ui::detail "$("$cmd" --version 2>&1 | head -1)"
  else
    ui::die "$cmd is required but not installed." "$hint"
  fi
}

check_soft_prereq() {
  local cmd="$1"
  local hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    ui::ok "$cmd found"
    ui::detail "$("$cmd" --version 2>&1 | head -1)"
  else
    ui::warn "$cmd not found"
    ui::hint "$hint"
    WARNED=$((WARNED + 1))
  fi
}

cmd_status() { command -v "$1" >/dev/null 2>&1 && echo "ok" || echo "warn"; }
cmd_value()  { command -v "$1" >/dev/null 2>&1 && command -v "$1" || echo "missing"; }
env_status() { [ -f ".env" ] && echo "ok" || echo "warn"; }
env_value()  { [ -f ".env" ] && echo "present" || echo "missing"; }

# --- Banner ------------------------------------------------------------------

ui::banner "make setup" "Setting up the Lunaris developer environment"

# --- Step 1: Hard prerequisites ---------------------------------------------

ui::step 1 5 "Hard prerequisites"

check_hard_prereq git  "Install: https://git-scm.com/downloads"
check_hard_prereq curl "Install: https://curl.se/download.html"
check_hard_prereq bash "Bash 3.2+ required (you are running this, so this should never fail)"

# --- Step 2: uv (Python package manager) ------------------------------------

ui::step 2 5 "uv (Python package manager)"

UV_BIN="${HOME}/.local/bin/uv"
if [ -x "$UV_BIN" ] || command -v uv >/dev/null 2>&1; then
  ui::skip "uv already installed ($("${UV_BIN}" --version 2>/dev/null || uv --version 2>/dev/null))"
  SKIPPED=$((SKIPPED + 1))
else
  if ! ui::run "Installing uv via curl" "curl -LsSf https://astral.sh/uv/install.sh | sh"; then
    ui::die "uv installation failed" \
            "Try the manual install: https://docs.astral.sh/uv/getting-started/installation/"
  fi
  INSTALLED=$((INSTALLED + 1))
fi

# Ensure uv is on PATH for the rest of this script (covers fresh-install case).
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  ui::die "uv was installed but is not on PATH" \
          "Add \$HOME/.local/bin to your shell PATH and re-run"
fi

# --- Step 3: Python workspace dependencies ----------------------------------

ui::step 3 5 "Python workspace dependencies"

if ! ui::run "uv sync --all-packages" "uv sync --all-packages"; then
  ui::die "Workspace sync failed" \
          "Common cause: a pyproject.toml syntax error in a workspace member"
fi
INSTALLED=$((INSTALLED + 1))

# --- Step 4: Web dependencies (apps/web) ------------------------------------

ui::step 4 5 "Web dependencies (apps/web)"

if [ ! -f "apps/web/package.json" ]; then
  ui::skip "apps/web not present — skipping web deps"
elif ! command -v npm >/dev/null 2>&1; then
  ui::warn "npm not installed — skipping web deps"
  ui::hint "Install Node.js (https://nodejs.org), then re-run 'make setup'"
  WARNED=$((WARNED + 1))
elif [ -d "apps/web/node_modules" ]; then
  ui::skip "apps/web/node_modules already present"
  SKIPPED=$((SKIPPED + 1))
else
  if ! ui::run "npm install (apps/web)" "cd apps/web && npm install"; then
    ui::warn "web dependency install failed; the web dev server will not start until resolved"
    WARNED=$((WARNED + 1))
  else
    INSTALLED=$((INSTALLED + 1))
  fi
fi

# --- Step 5: Soft prerequisites + .env --------------------------------------

ui::step 5 5 "Soft prerequisites + .env"

if [ -f ".env" ]; then
  ui::skip ".env already exists"
elif [ -f ".env.sample" ]; then
  cp .env.sample .env
  ui::ok ".env created from .env.sample"
  ui::hint "Edit .env to set ANTHROPIC_API_KEY (live pipeline) and Supabase keys"
else
  ui::warn ".env.sample not found; skipping .env generation"
  WARNED=$((WARNED + 1))
fi

check_soft_prereq docker   "Needed by 'make start' (the local Supabase stack). Install Docker Desktop: https://www.docker.com/products/docker-desktop"
check_soft_prereq supabase "The local Postgres + pgvector data layer. Install: https://supabase.com/docs/guides/cli"
check_soft_prereq node     "Needed by apps/web. Install: https://nodejs.org"

# --- Summary dashboard ------------------------------------------------------

PKG_COUNT="$(uv pip list 2>/dev/null | tail -n +3 | wc -l | tr -d ' ')"
WEB_DEPS="missing"
[ -d "apps/web/node_modules" ] && WEB_DEPS="installed"

ui::summary_begin "Installation Summary"
ui::summary_row "uv"               "$(uv --version 2>/dev/null | awk '{print $2}')" "ok"
ui::summary_row "Python workspace" "${PKG_COUNT} packages installed"                "ok"
ui::summary_row "web deps"         "${WEB_DEPS}"                  "$([ "$WEB_DEPS" = "installed" ] && echo ok || echo warn)"
ui::summary_row "docker"           "$(cmd_value docker)"          "$(cmd_status docker)"
ui::summary_row "supabase CLI"     "$(cmd_value supabase)"        "$(cmd_status supabase)"
ui::summary_row "node"             "$(cmd_value node)"            "$(cmd_status node)"
ui::summary_row ".env"             "$(env_value)"                 "$(env_status)"
ui::summary_end

printf "  %s%s installed · %s skipped · %s warnings%s\n" \
  "${UI_DIM}" "$INSTALLED" "$SKIPPED" "$WARNED" "${UI_RESET}"
printf "  %sNext: '%smake start%s' (backend) or '%smake run%s' (everything).%s\n\n" \
  "${UI_DIM}" "${UI_PRIMARY}" "${UI_DIM}" "${UI_PRIMARY}" "${UI_DIM}" "${UI_RESET}"
