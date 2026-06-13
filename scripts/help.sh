#!/usr/bin/env bash
# scripts/help.sh — render the formatted `make help` reference.
#
# Wired by the Makefile's default `help` target. Lists every target the
# Makefile defines; keep it in sync whenever a target is added or removed.

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"

ui::_logo
printf "\n  %s%slunaris%s %s— make targets · turn a topic into a verified course%s\n" \
  "${UI_BOLD}" "${UI_PRIMARY}" "${UI_RESET}" \
  "${UI_DIM}" "${UI_RESET}"

ui::section "Help"
ui::cmd "make help"          "Print this command reference (default)"

ui::section "Setup & Run"
ui::cmd "make setup"         "Install dev dependencies (uv, web, .env) — idempotent"
ui::cmd "make start"         "Start the backend (port-check + supabase + api, health-gated)"
ui::cmd "make start-all"     "Start the full stack (supabase + api + web)"
ui::cmd "make run"           "Bulletproof end-to-end: setup + start-all"
ui::cmd "make stop"          "Stop all services (Supabase data preserved)"

ui::section "Diagnostics"
ui::cmd "make check-ports"   "Pre-flight the fixed Supabase ports (54321-3)"

ui::section "Video"
ui::cmd "make video-deps"    "Install the local render toolchain (Manim CE; verifies ffmpeg)"

ui::section "Testing"
ui::cmd "make test"          "Run the standard suites: Python + web"
ui::cmd "make test-python"   "Deterministic Python suite only (pytest)"
ui::cmd "make test-web"      "Web suite only (Vitest)"
ui::cmd "make test-eval"     "Live Claude evals (opt-in; needs ANTHROPIC_API_KEY)"

ui::section "Linting"
ui::cmd "make lint"          "Run all linters (ruff, web, supabase db lint)"
ui::cmd "make lint-fix"      "Auto-fix linting issues where supported"

printf "\n  %sPipeline mode: the API serves the deterministic stub by default;%s\n" "${UI_DIM}" "${UI_RESET}"
printf "  %sset %sLUNARIS_PIPELINE=live%s (with ANTHROPIC_API_KEY in .env) for real Claude.%s\n\n" \
  "${UI_DIM}" "${UI_PRIMARY}" "${UI_DIM}" "${UI_RESET}"
