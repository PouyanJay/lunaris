#!/usr/bin/env bash
# scripts/check-ports.sh — Supabase infra-port pre-flight for `make start`.
#
# Checks ONLY the fixed Supabase ports — the ones the Supabase CLI binds from
# supabase/config.toml (54321/54322/54323). These CANNOT be relocated: the
# project's URLs and keys are configured against them, so a conflict must be
# resolved by freeing the port, not by moving the data layer.
#
# (The API and web ports are NOT checked here — run.sh resolves those itself
# at launch and can fall back to a new free port, since it owns those processes.)
#
# Resolution, safest reasonable default:
#   - Our own Lunaris container (Supabase project "lunaris") holding a port →
#     silently skipped; `supabase start` reuses/replaces it naturally.
#   - Foreign Docker container (e.g. another project's Supabase stack, like
#     opensina, which also wants 54321/54322) → on a TTY, prompts `[y/N]`
#     (default No) to STOP it. Containers are stopped (NOT removed), so the
#     other project's data survives and `docker start <name>` restores it.
#     Non-TTY (CI) aborts unless LUNARIS_AUTO_STOP_CONFLICTS=1.
#   - Non-Docker host process (a host Postgres, …) → diagnostic only. We NEVER
#     kill arbitrary host processes by PID; the user must stop it.
#
# Exit codes:
#   0 = every port is available (or conflicts were resolved successfully)
#   1 = at least one conflict remains unresolved; do not start the stack
#   2 = invocation error (bad args)
#
# Run via: scripts/check-ports.sh   |   scripts/check-ports.sh --self-test
# Compatibility: Bash 3.2 (stock macOS bash).

set -euo pipefail

# `lsof` lives in /usr/sbin on macOS and is often absent from a restricted
# PATH (CI, a pytest subprocess). Prepend system paths so the script is
# self-sufficient regardless of how it's invoked.
export PATH="/usr/sbin:/sbin:${PATH:-/usr/local/bin:/usr/bin:/bin}"

source "$(dirname "$0")/lib/ui.sh"

# --- Defaults ---------------------------------------------------------------

# Each entry: "<port> <label>". The fixed Supabase ports only — see the header
# note on why api/web are resolved by run.sh instead.
DEFAULT_PORT_TABLE='
54321 supabase-api
54322 supabase-db
54323 supabase-studio
'

# Override via env / .env (loaded by the caller). Empty = use the default.
PORT_TABLE="${LUNARIS_PORT_TABLE:-$DEFAULT_PORT_TABLE}"

# When set to 1, prompts are skipped — foreign Docker containers are
# auto-stopped without asking. Honored in non-TTY mode (CI) or on opt-in.
# Non-Docker holders still abort the run.
AUTO_STOP="${LUNARIS_AUTO_STOP_CONFLICTS:-0}"

# The Supabase CLI project id that identifies OUR containers (supabase/config.toml
# → project_id = "lunaris"). Set on each container as both
# com.docker.compose.project and com.supabase.cli.project.
LUNARIS_PROJECT_LABEL="lunaris"

# --- Argument parsing -------------------------------------------------------

SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --self-test) SELF_TEST=1 ;;
    -h|--help)
      cat <<EOF
Usage: scripts/check-ports.sh [--self-test]

Pre-flight for the fixed Supabase ports (54321/54322/54323) before
\`make start\`. These can't be relocated; the API/web ports are resolved by
run.sh, which can fall back to a free port.

Behavior:
  - Free / lunaris-owned ports: silently passed.
  - Foreign Docker containers: TTY prompts y/N to stop them (data preserved).
    Non-TTY aborts unless LUNARIS_AUTO_STOP_CONFLICTS=1.
  - Non-Docker processes: diagnostic only; never auto-stopped.

Environment overrides:
  LUNARIS_PORT_TABLE              Newline-separated "<port> <label>" lines.
                                  Default: 54321/54322/54323 (Supabase).
  LUNARIS_AUTO_STOP_CONFLICTS=1   Skip prompts; auto-stop foreign Docker.

Exit codes:
  0  all ports available (or conflicts resolved)
  1  at least one conflict remains
  2  bad args
EOF
      exit 0
      ;;
    *)
      printf "ERROR: unknown argument: %s\n" "$1" >&2
      exit 2
      ;;
  esac
  shift
done

# --- Port-holder classification ---------------------------------------------

# Echo the PID LISTENING on $1 (listeners only), or empty if free.
#
# `-sTCP:LISTEN` is load-bearing: without it `lsof -ti :PORT` also matches a
# socket where PORT is the REMOTE endpoint, so a process that merely connected
# to the port (a lingering CLOSE_WAIT) is misread as holding it. Only a
# listener actually occupies a host port — that is the real conflict.
holder_pid() {
  lsof -ti ":$1" -sTCP:LISTEN 2>/dev/null | head -n 1
}

# Find a docker container publishing host port $1. Echoes "name|project" or
# empty. Uses `docker ps --filter publish=<port>` (portable across versions).
holder_docker() {
  local port="$1"
  docker ps --filter "publish=${port}" \
            --format '{{.Names}}|{{.Label "com.docker.compose.project"}}' \
            2>/dev/null | head -n 1
}

# Echo "<pid>:<command>" for a non-docker holder of port $1.
holder_process() {
  local port="$1"
  local pid
  pid="$(holder_pid "$port")"
  if [ -z "$pid" ]; then return; fi
  printf "%s:%s\n" "$pid" "$(ps -o comm= -p "$pid" 2>/dev/null | head -n 1)"
}

# Classify port $1 → echoes one of:
#   "free" | "lunaris|<container>" | "foreign-docker|<container>|<project>"
#   | "non-docker|<pid>:<command>"
classify_port() {
  local port="$1"
  local pid
  pid="$(holder_pid "$port")"
  if [ -z "$pid" ]; then
    printf "free\n"
    return
  fi
  local docker_info
  docker_info="$(holder_docker "$port")"
  if [ -n "$docker_info" ]; then
    local container project
    container="${docker_info%%|*}"
    project="${docker_info##*|}"
    if [ "$project" = "$LUNARIS_PROJECT_LABEL" ]; then
      printf "lunaris|%s\n" "$container"
    else
      printf "foreign-docker|%s|%s\n" "$container" "${project:-<no-project>}"
    fi
  else
    printf "non-docker|%s\n" "$(holder_process "$port")"
  fi
}

# --- Interactive helpers ----------------------------------------------------

is_interactive() { [ -t 0 ] && [ -t 1 ]; }

# Prompt y/N, default No. Returns 0 for yes, 1 for no.
confirm_stop() {
  local prompt="$1"
  local answer
  printf "%s [y/N] " "$prompt"
  if ! read -r answer; then
    return 1
  fi
  case "$(printf "%s" "$answer" | tr 'A-Z' 'a-z')" in
    y|yes) return 0 ;;
    *)     return 1 ;;
  esac
}

# --- Resolution logic -------------------------------------------------------

STOPPED_CONTAINERS=""
STILL_BLOCKING=""   # port→remediation pairs, newline-separated

stop_container() {
  local name="$1"
  if docker stop "$name" >/dev/null 2>&1; then
    STOPPED_CONTAINERS="${STOPPED_CONTAINERS} ${name}"
    return 0
  fi
  return 1
}

# Resolve a single port. Returns 0 if now free (or ours), 1 if still blocked.
resolve_port() {
  local port="$1"
  local label="$2"
  local kind
  kind="$(classify_port "$port")"
  case "$kind" in
    free)
      ui::skip "${label} (port ${port}): free"
      return 0
      ;;
    lunaris\|*)
      local container="${kind#lunaris|}"
      ui::skip "${label} (port ${port}): own container ${container} (will be reused)"
      return 0
      ;;
    foreign-docker\|*)
      local rest="${kind#foreign-docker|}"
      local container="${rest%%|*}"
      local project="${rest##*|}"
      ui::warn "${label} (port ${port}): held by container '${container}' (project: ${project})"
      if [ "$AUTO_STOP" = "1" ] || ! is_interactive; then
        if [ "$AUTO_STOP" = "1" ]; then
          ui::info "LUNARIS_AUTO_STOP_CONFLICTS=1 — stopping ${container}"
        else
          ui::warn "non-interactive shell — set LUNARIS_AUTO_STOP_CONFLICTS=1 to auto-stop, or stop manually"
          STILL_BLOCKING="${STILL_BLOCKING}
  ${port}  →  docker stop ${container}     # container project: ${project}"
          return 1
        fi
        if stop_container "$container"; then
          ui::ok "stopped ${container} (data preserved; \`docker start ${container}\` to restore)"
          return 0
        fi
        ui::fail "failed to stop ${container}"
        STILL_BLOCKING="${STILL_BLOCKING}
  ${port}  →  docker stop ${container}     # tried + failed — try manually"
        return 1
      fi
      if confirm_stop "    Stop container '${container}' to free port ${port}? (data preserved)"; then
        if stop_container "$container"; then
          ui::ok "stopped ${container} (\`docker start ${container}\` to restore)"
          return 0
        fi
        ui::fail "failed to stop ${container}"
        STILL_BLOCKING="${STILL_BLOCKING}
  ${port}  →  docker stop ${container}     # tried + failed — try manually"
        return 1
      fi
      ui::skip "declined"
      STILL_BLOCKING="${STILL_BLOCKING}
  ${port}  →  docker stop ${container}     # you declined the stop prompt"
      return 1
      ;;
    non-docker\|*)
      local proc_info="${kind#non-docker|}"
      local pid="${proc_info%%:*}"
      local cmd="${proc_info##*:}"
      ui::fail "${label} (port ${port}): held by non-Docker process pid=${pid} cmd=${cmd}"
      ui::hint "we never auto-stop host processes — stop it manually if it's safe"
      STILL_BLOCKING="${STILL_BLOCKING}
  ${port}  →  kill ${pid}     # process: ${cmd} — verify before killing!"
      return 1
      ;;
    *)
      ui::fail "${label} (port ${port}): unexpected classification: ${kind}"
      return 1
      ;;
  esac
}

# --- Self-test (no side effects) --------------------------------------------

self_test() {
  ui::section "Port-check self-test"
  ui::info "classify a known-free high port"
  local kind
  kind="$(classify_port 49157)"
  if [ "$kind" = "free" ]; then
    ui::ok "free port classified correctly"
  else
    ui::fail "expected 'free', got '${kind}'"
    return 1
  fi
  ui::info "lookup tools available"
  command -v lsof   >/dev/null 2>&1 && ui::ok "lsof"   || { ui::fail "lsof missing";   return 1; }
  command -v docker >/dev/null 2>&1 && ui::ok "docker" || ui::warn "docker missing (foreign-container resolution disabled)"
  ui::ok "self-test passed"
}

# --- Main -------------------------------------------------------------------

ui::init

if [ "$SELF_TEST" = "1" ]; then
  self_test
  exit $?
fi

ui::section "Supabase port pre-flight"

EXIT_CODE=0
while IFS=' ' read -r port label; do
  [ -z "$port" ] && continue
  if ! resolve_port "$port" "$label"; then
    EXIT_CODE=1
  fi
done <<EOF
$(printf "%s\n" "$PORT_TABLE" | grep -E '^[[:space:]]*[0-9]+' || true)
EOF

# --- Summary ----------------------------------------------------------------

if [ -n "$STOPPED_CONTAINERS" ]; then
  ui::info "Stopped containers:${STOPPED_CONTAINERS}"
  ui::hint "restart any of them with: docker start <name>"
fi

if [ $EXIT_CODE -ne 0 ]; then
  # Deliberate stop — not a crash. Frame as "needs your input" so CI logs and
  # users don't mistake the non-zero exit for a bug.
  ui::section "Stopped — port(s) still blocked, free them and re-run"
  printf "%s\n\n" "$STILL_BLOCKING"
  ui::hint "Then re-run: make start"

  RULE="$(ui::_repeat_char "─" 70)"
  printf "\n  %s%s%s\n" "${UI_DIM}" "${RULE}" "${UI_RESET}"
  printf "  %s%s  Deliberate stop — this is NOT a crash.%s\n" \
    "${UI_PRIMARY}${UI_BOLD}" "${UI_ICON_PAUSE}" "${UI_RESET}"
  printf "  %s   The %s'make: *** [start] Error 1'%s%s line that follows is the\n" \
    "${UI_DIM}" "${UI_BOLD}" "${UI_RESET}" "${UI_DIM}"
  printf "  %s   standard exit-code signal CI relies on. Expected here —\n" "${UI_DIM}"
  printf "  %s   re-run after freeing the port(s) listed above.%s\n" "${UI_DIM}" "${UI_RESET}"
  printf "  %s%s%s\n\n" "${UI_DIM}" "${RULE}" "${UI_RESET}"
  exit 1
fi

ui::ok "all ports clear"
exit 0
