#!/usr/bin/env bash
# scripts/run.sh — start (or stop) the Lunaris stack end to end.
#
# Run via: make run | make start | make start-all | make stop
#
# The Lunaris runtime is three layers:
#   1. supabase — local Postgres + pgvector data layer (Supabase CLI; runs in Docker).
#   2. api      — the FastAPI delivery service (standalone uvicorn process).
#   3. web      — the Vite + React prerequisite-graph explorer (dev server).
#
# The API + web run as background host processes; their state lives under
# .run-state/ (gitignored):
#   .run-state/<service>.pid   — PID for a clean --stop
#   .run-state/<service>.log   — captured stdout+stderr
# Supabase is managed by its own CLI (`supabase start` / `supabase stop`).
#
# Pipeline mode: by default this serves the REAL deep-agent harness
# (LUNARIS_PIPELINE=agent) when a usable ANTHROPIC_API_KEY is reachable (process
# env, .env, or the Settings secret store). With no key it falls back to the
# deterministic stub (no key, instant, always works) and says so. Override
# explicitly with LUNARIS_PIPELINE=agent|live|stub.

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"
ui::init

# `lsof` lives in /usr/sbin on macOS and is often off a restricted PATH.
export PATH="/usr/sbin:/sbin:${PATH}"

# --- Defaults & argument parsing --------------------------------------------

WANT_SUPABASE=1
WANT_API=1
WANT_WEB=1
ACTION="start"

API_HOST="127.0.0.1"
API_PORT="${LUNARIS_API_PORT:-8000}"
WEB_PORT="${LUNARIS_WEB_PORT:-5173}"
SUPABASE_REST="http://127.0.0.1:54321/rest/v1/"
# The explicit pipeline override, if any. When empty it is resolved by a key guard
# (resolve_pipeline) AFTER the .env file exists — default 'agent', falling back to 'stub'.
PIPELINE="${LUNARIS_PIPELINE:-}"
PIPELINE_FELL_BACK=0
# The .env.sample placeholder — treated as "no key", so a fresh checkout falls back to stub.
ANTHROPIC_KEY_PLACEHOLDER="sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

print_help() {
  cat <<EOF
Usage: scripts/run.sh [options]

Start (or stop) the Lunaris stack end to end.

Options:
  (no flags)         Start everything: supabase + api + web
  --backend-only     Start the backend only (supabase + api; no web dev server)
  --frontend-only    Start the web dev server only (assumes api is up)
  --skip-supabase    Start everything except the Supabase data layer
  --skip-api         Start everything except the API
  --skip-web         Start everything except the web dev server
  --stop             Stop all services and clean up
  -h, --help         Show this help

Environment:
  LUNARIS_PIPELINE   API pipeline backend: 'agent' (default — the real deep-agent
                     harness; needs ANTHROPIC_API_KEY), 'live' (legacy single-shot
                     orchestrator, also needs a key), or 'stub' (deterministic, no
                     key). With no key reachable the default falls back to 'stub'.
  LUNARIS_API_PORT   API port (default 8000).
  LUNARIS_WEB_PORT   Web dev-server port (default 5173).

Background process state:
  .run-state/<service>.pid   PID file (for clean --stop)
  .run-state/<service>.log   Captured stdout+stderr

Examples:
  scripts/run.sh                       # everything (supabase + api + web)
  LUNARIS_PIPELINE=stub scripts/run.sh # force the deterministic no-key pipeline
  scripts/run.sh --backend-only        # supabase + api, no web
  scripts/run.sh --stop                # tear down
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)       print_help; exit 0 ;;
    --backend-only)  WANT_SUPABASE=1; WANT_API=1; WANT_WEB=0 ;;
    --frontend-only) WANT_SUPABASE=0; WANT_API=0; WANT_WEB=1 ;;
    --skip-supabase) WANT_SUPABASE=0 ;;
    --skip-api)      WANT_API=0 ;;
    --skip-web)      WANT_WEB=0 ;;
    --stop)          ACTION="stop" ;;
    *)
      printf "ERROR: unknown argument: %s\n" "$1" >&2
      printf "Run with --help for usage.\n" >&2
      exit 2
      ;;
  esac
  shift
done

# --- State directory --------------------------------------------------------

RUN_STATE_DIR=".run-state"
mkdir -p "$RUN_STATE_DIR"

# --- Helpers ----------------------------------------------------------------

# reap_service "name" — kill our own background process at
# .run-state/<name>.pid if it's still alive, and clear the pidfile. Quiet:
# used at the top of the start path so a re-run is a clean restart and the
# port pre-flight doesn't flag our OWN stale process as a conflict.
reap_service() {
  local name="$1"
  local pidfile="${RUN_STATE_DIR}/${name}.pid"
  [ -f "$pidfile" ] || return 0
  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}

# stop_service "name" "status_var" "severity_var" — kill the PID at
# .run-state/<name>.pid (if any) and report the real per-service outcome via
# the named caller variables, so the summary reflects what actually happened.
stop_service() {
  local name="$1"
  local status_var="$2"
  local sev_var="$3"
  local pidfile="${RUN_STATE_DIR}/${name}.pid"
  local status sev

  if [ -f "$pidfile" ]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      ui::ok "${name} stopped (PID ${pid})"
      status="stopped (PID ${pid})"; sev="ok"
    else
      ui::skip "${name} pidfile stale (cleaned)"
      status="stale pidfile cleaned"; sev="skip"
    fi
    rm -f "$pidfile"
  else
    ui::skip "${name} not running"
    status="not running"; sev="skip"
  fi

  printf -v "$status_var" "%s" "$status"
  printf -v "$sev_var" "%s" "$sev"
}

# _poll_url_ready "url" timeout_s — return 0 once the URL answers (any HTTP
# response, including 401/404 — the server is up), 2 if it never does in time.
_poll_url_ready() {
  local url="$1"
  local deadline=$((SECONDS + ${2:-30}))
  while [ "$SECONDS" -lt "$deadline" ]; do
    curl -fsS -o /dev/null "$url" 2>/dev/null && return 0
    # A 401/404 still proves the port is bound and serving.
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
    [ "$code" != "000" ] && return 0
    sleep 1
  done
  return 2
}

# --- Service-port resolution (api / web) ------------------------------------
# The API and web are processes WE launch, so a port conflict can be resolved
# by asking and then either stopping the holder or relocating to a free port —
# the behaviour requested for `make start`. (Supabase ports are fixed and are
# handled by check-ports.sh instead.)

# is_interactive — true iff we can prompt. Tests stdin + STDERR (not stdout):
# resolve_service_port runs inside $(...), so fd1 is a pipe even on a real
# terminal — stderr is where the prompt actually goes.
is_interactive() { [ -t 0 ] && [ -t 2 ]; }

# confirm "prompt" — y/N, default No. Prompt goes to stderr so it stays visible
# (and uncaptured) when this runs inside a command substitution.
confirm() {
  local answer
  printf "%s [y/N] " "$1" >&2
  read -r answer || return 1
  case "$(printf "%s" "$answer" | tr 'A-Z' 'a-z')" in
    y|yes) return 0 ;;
    *)     return 1 ;;
  esac
}

# port_listener_pid PORT — PID listening on PORT (listeners only), or empty.
port_listener_pid() { lsof -ti ":$1" -sTCP:LISTEN 2>/dev/null | head -n 1; }

# pick_free_port START — first free TCP port at or above START (scans up to +50).
pick_free_port() {
  local p="$1"
  local max=$(( $1 + 50 ))
  while [ "$p" -lt "$max" ]; do
    [ -z "$(port_listener_pid "$p")" ] && { printf "%s" "$p"; return 0; }
    p=$((p + 1))
  done
  printf "%s" "$1"; return 1
}

# resolve_service_port DESIRED LABEL — choose the port to bind for a service we
# launch. Our own stale instance is already reaped, so any holder is foreign.
#   free                   → use DESIRED
#   held + you say yes     → stop the holder (docker stop / kill pid), use DESIRED
#   held + you say no      → fall back to the next free port, serve there
#   held + non-interactive → fall back to a free port (never kill blind in CI)
# Echoes the chosen port on STDOUT; all prompts/status go to STDERR so the
# captured value stays clean.
resolve_service_port() {
  local desired="$1"
  local label="$2"
  local pid
  pid="$(port_listener_pid "$desired")"
  if [ -z "$pid" ]; then
    printf "%s" "$desired"; return 0
  fi

  local container
  container="$(docker ps --filter "publish=${desired}" --format '{{.Names}}' 2>/dev/null | head -n 1)"
  local holder
  if [ -n "$container" ]; then
    holder="container '${container}'"
  else
    holder="process pid=${pid} ($(ps -o comm= -p "$pid" 2>/dev/null | head -n 1))"
  fi
  ui::warn "${label}: port ${desired} is in use by ${holder}" >&2

  if is_interactive && confirm "    Stop it and take port ${desired}?  (No = serve on a new free port)"; then
    if [ -n "$container" ]; then
      docker stop "$container" >/dev/null 2>&1 \
        && ui::ok "stopped ${container} (\`docker start ${container}\` to restore)" >&2 \
        || ui::warn "could not stop ${container} — relocating instead" >&2
    else
      kill "$pid" 2>/dev/null \
        && ui::ok "stopped ${holder}" >&2 \
        || ui::warn "could not stop pid ${pid} — relocating instead" >&2
    fi
    sleep 1
    if [ -z "$(port_listener_pid "$desired")" ]; then
      printf "%s" "$desired"; return 0
    fi
    ui::warn "port ${desired} still held — relocating" >&2
  fi

  local alt
  alt="$(pick_free_port $((desired + 1)))"
  ui::info "${label}: serving on free port ${alt} (instead of ${desired})" >&2
  printf "%s" "$alt"
}

# --- Pipeline resolution (key guard) ----------------------------------------
# The agent/live pipelines need a real Anthropic key; the stub needs none. To make
# `make run` "live by default but never broken", we default to the real agent harness
# only when a usable key is reachable, and otherwise fall back to the stub with a clear
# message. An explicit LUNARIS_PIPELINE always wins (no guard, operator's choice).

# anthropic_key_present — 0 iff a usable ANTHROPIC_API_KEY is reachable from any of the
# sources the API will see at startup: the process env, the .env file (loaded via
# --env-file), or the Settings secret store (.secrets/secrets.json, applied to env on
# API startup). The .env.sample placeholder counts as "no key".
anthropic_key_present() {
  if [ -n "${ANTHROPIC_API_KEY:-}" ] && [ "${ANTHROPIC_API_KEY}" != "$ANTHROPIC_KEY_PLACEHOLDER" ]; then
    return 0
  fi
  if [ -f ".env" ]; then
    local value
    value="$(grep -E '^[[:space:]]*ANTHROPIC_API_KEY=' .env | tail -n 1 | cut -d= -f2-)"
    value="${value%\"}"; value="${value#\"}"   # strip surrounding double quotes, if any
    value="${value%\'}"; value="${value#\'}"   # and single quotes
    if [ -n "$value" ] && [ "$value" != "$ANTHROPIC_KEY_PLACEHOLDER" ]; then
      return 0
    fi
  fi
  local secrets="${LUNARIS_SECRETS_PATH:-.secrets/secrets.json}"
  if [ -f "$secrets" ] && grep -q "ANTHROPIC_API_KEY" "$secrets" 2>/dev/null; then
    return 0
  fi
  return 1
}

# resolve_pipeline — set PIPELINE (and PIPELINE_FELL_BACK) honoring an explicit override,
# else defaulting to 'agent' guarded by anthropic_key_present (→ 'stub' when no key).
resolve_pipeline() {
  if [ -n "$PIPELINE" ]; then
    return 0   # explicit LUNARIS_PIPELINE — honor it verbatim
  fi
  if anthropic_key_present; then
    PIPELINE="agent"
  else
    PIPELINE="stub"
    PIPELINE_FELL_BACK=1
  fi
}

# start_supabase — bring up the local Supabase stack via its CLI (idempotent:
# a second `supabase start` just reports the running stack). Migrations apply
# on first start. Returns 0 (up), 1 (could not start).
start_supabase() {
  if ! command -v supabase >/dev/null 2>&1; then
    ui::warn "supabase CLI not installed — skipping the data layer"
    ui::hint "Install: https://supabase.com/docs/guides/cli (then 'make start')"
    return 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    ui::warn "docker not installed — Supabase cannot start"
    ui::hint "Install Docker Desktop: https://www.docker.com/products/docker-desktop"
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    ui::fail "Docker is installed but not running"
    ui::hint "Start it: open -a Docker  (wait ~10s, then re-run 'make start')"
    return 1
  fi

  # Free any foreign container holding our Supabase ports (e.g. another
  # project's Supabase stack on 54321/54322) before `supabase start` binds them.
  # check-ports.sh asks to stop it; if the conflict isn't resolved (declined, or
  # CI without auto-stop) the Supabase ports are fixed and can't be relocated, so
  # we fail the whole start with a clear message rather than limping on without
  # the data layer. (ui::die exits — Supabase is step 1, nothing started yet.)
  if [ -x "$(dirname "$0")/check-ports.sh" ]; then
    if ! "$(dirname "$0")/check-ports.sh"; then
      ui::die "Supabase port conflict not resolved — Lunaris cannot start" \
              "See the message above: answer 'y' to stop the other stack, or free the port(s)"
    fi
  fi

  if ! ui::run "supabase start (Postgres + pgvector + migrations)" "supabase start"; then
    # Self-heal a stale/partial stack. The CLI refuses with "supabase start is
    # already running" while a core container (db/kong) has actually exited
    # (137 = OOM / forced stop, common after the host sleeps or Docker is
    # memory-pressured). A clean `supabase stop` tears the partial stack down
    # (the database VOLUME is preserved), so a retry comes up healthy.
    ui::warn "supabase start failed — recovering a stale/partial stack (data preserved)"
    ui::run "supabase stop (cleanup)" "supabase stop" || true
    if ! ui::run "supabase start (retry after cleanup)" "supabase start"; then
      ui::hint "Inspect: docker ps -a --filter name=supabase_  ·  supabase start --debug"
      return 1
    fi
  fi

  if _poll_url_ready "$SUPABASE_REST" 60; then
    ui::ok "Supabase REST ready at ${SUPABASE_REST}"
    return 0
  fi
  ui::warn "Supabase started but REST endpoint not yet answering — see 'supabase status'"
  return 0
}

# start_api — launch the FastAPI delivery service (standalone uvicorn) as a
# background process, recording PID + log under .run-state. Health-gates on
# /api/healthz. Returns 0 (ready), 2 (launched, not yet answering), 1 (no launch).
start_api() {
  if ! command -v uv >/dev/null 2>&1; then
    ui::warn "uv not installed — skipping the API"
    ui::hint "Run 'make setup' first"
    return 1
  fi

  # Resolve the port (ask → stop the holder, or relocate to a free port).
  API_PORT="$(resolve_service_port "$API_PORT" "api")"

  local env_flag=""
  [ -f ".env" ] && env_flag="--env-file .env"

  local root="$PWD"
  local log="${root}/${RUN_STATE_DIR}/api.log"

  if [ "$PIPELINE_FELL_BACK" = "1" ]; then
    ui::warn "pipeline mode: stub — no ANTHROPIC_API_KEY found, so the real agent harness is off"
    ui::hint "Add ANTHROPIC_API_KEY to .env (or set it in the Settings panel) for the live agent"
  elif [ "$PIPELINE" = "stub" ]; then
    ui::info "pipeline mode: stub  (deterministic, no key; unset LUNARIS_PIPELINE for the live agent)"
  else
    ui::info "pipeline mode: ${PIPELINE}  (real Claude — the deep-agent harness)"
  fi

  # Launch in run.sh's own shell so $! is the uvicorn PID; SIGTERM to it stops
  # the server cleanly. Env is exported inline so the child inherits the mode.
  LUNARIS_PIPELINE="$PIPELINE" LUNARIS_COURSE_DIR="${LUNARIS_COURSE_DIR:-.courses}" \
    nohup uv run $env_flag uvicorn lunaris_api.main:app \
      --host "$API_HOST" --port "$API_PORT" >"$log" 2>&1 &
  local pid=$!
  echo "$pid" >"${root}/${RUN_STATE_DIR}/api.pid"

  if _poll_url_ready "http://${API_HOST}:${API_PORT}/api/healthz" 30; then
    ui::ok "API ready at http://${API_HOST}:${API_PORT} (PID ${pid})"
    return 0
  fi
  ui::warn "API starting (PID ${pid}) — not yet answering; see ${log}"
  return 2
}

# start_web — launch the Vite dev server (apps/web) as a background process,
# pointed at the local API via VITE_API_URL. Returns 0 (ready), 2 (launched,
# not yet ready), 1 (could not launch).
start_web() {
  if [ ! -f "apps/web/package.json" ]; then
    ui::warn "apps/web not present — skipping the web dev server"
    return 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    ui::warn "npm not installed — skipping the web dev server"
    ui::hint "Install Node.js: https://nodejs.org"
    return 1
  fi
  [ -d "apps/web/node_modules" ] || ui::run "npm install (apps/web)" "cd apps/web && npm install"

  # Resolve the port (ask → stop the holder, or relocate to a free port).
  WEB_PORT="$(resolve_service_port "$WEB_PORT" "web")"

  local root="$PWD"
  local log="${root}/${RUN_STATE_DIR}/web.log"
  # cd into apps/web so $! is npm's PID (SIGTERM cascades to the Vite child via
  # npm's process group), then cd back so the rest of the script is unaffected.
  # --strictPort: bind exactly the port we resolved (don't let Vite silently
  # pick a different one, which would desync the reported port + readiness poll).
  # VITE_API_URL points the web app at the API's actual (possibly relocated) port.
  cd apps/web
  VITE_API_URL="http://${API_HOST}:${API_PORT}" nohup npm run dev -- --port "$WEB_PORT" --strictPort >"$log" 2>&1 &
  local pid=$!
  cd "$root"
  echo "$pid" >"${root}/${RUN_STATE_DIR}/web.pid"

  if _poll_url_ready "http://localhost:${WEB_PORT}" 30; then
    ui::ok "web dev server ready at http://localhost:${WEB_PORT} (PID ${pid})"
    return 0
  fi
  ui::warn "web dev server starting (PID ${pid}) — not yet answering; see ${log}"
  return 2
}

# --- Banner -----------------------------------------------------------------

if [ "$ACTION" = "stop" ]; then
  ui::banner "make stop" "Tearing down the Lunaris stack"
else
  ui::banner "make start" "Starting the Lunaris stack"
fi

# --- Stop path --------------------------------------------------------------

if [ "$ACTION" = "stop" ]; then
  ui::step 1 1 "Stopping services"

  API_STATUS=""; API_SEV=""
  WEB_STATUS=""; WEB_SEV=""
  SUPABASE_STATUS="idle"; SUPABASE_SEV="skip"

  stop_service "web" WEB_STATUS WEB_SEV
  stop_service "api" API_STATUS API_SEV

  # Supabase is CLI-managed, not a pidfile service. `supabase stop` preserves
  # the database volume (data survives; `supabase start` restores it).
  if command -v supabase >/dev/null 2>&1 && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if ui::run "supabase stop (data preserved)" "supabase stop"; then
      SUPABASE_STATUS="stopped"; SUPABASE_SEV="ok"
    else
      SUPABASE_STATUS="not running"; SUPABASE_SEV="skip"
    fi
  else
    ui::skip "supabase: CLI or Docker unavailable — nothing to stop"
    SUPABASE_STATUS="unavailable"; SUPABASE_SEV="skip"
  fi

  ui::summary_begin "Shutdown Summary"
  ui::summary_row "web"      "$WEB_STATUS"      "$WEB_SEV"
  ui::summary_row "api"      "$API_STATUS"      "$API_SEV"
  ui::summary_row "supabase" "$SUPABASE_STATUS" "$SUPABASE_SEV"
  ui::summary_end
  exit 0
fi

# --- Start path: .env -------------------------------------------------------

if [ ! -f ".env" ]; then
  if [ -f ".env.sample" ]; then
    cp .env.sample .env
    ui::info ".env created from .env.sample"
    ui::hint "Edit .env to set ANTHROPIC_API_KEY for the real agent pipeline (else it runs the stub)"
  else
    ui::warn ".env not found and .env.sample missing — services will use defaults"
  fi
fi

# Resolve the pipeline now that .env exists: default to the real agent harness when a
# key is reachable, else fall back to the stub (announced below at the API step).
resolve_pipeline

# Reap our OWN stale api/web processes first, so a re-run is a clean restart
# and the port pre-flight only flags genuinely foreign conflicts.
reap_service "api"
reap_service "web"

# --- Start path: per-service ------------------------------------------------

STEPS=$((WANT_SUPABASE + WANT_API + WANT_WEB))
[ "$STEPS" -eq 0 ] && ui::die "No services selected — nothing to start" \
                              "Remove --skip-* flags or pass --help for usage"
CURRENT=0

SUPABASE_STATUS="skipped"; SUPABASE_SEV="skip"
API_STATUS="skipped";      API_SEV="skip"
WEB_STATUS="skipped";      WEB_SEV="skip"

if [ "$WANT_SUPABASE" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "supabase (Postgres + pgvector data layer)"
  if start_supabase; then
    SUPABASE_STATUS="running"; SUPABASE_SEV="ok"
  else
    # The data layer underpins the API's grounding retrieval. Without it the
    # stub pipeline still runs (grounding degrades to CUT), so warn — don't abort.
    ui::warn "Supabase did not start — the API will run, but grounding will be unavailable"
    SUPABASE_STATUS="not started"; SUPABASE_SEV="warn"
  fi
fi

if [ "$WANT_API" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "api (FastAPI delivery service — uvicorn)"
  api_rc=0
  start_api || api_rc=$?
  case "$api_rc" in
    0) API_STATUS="http://${API_HOST}:${API_PORT} (${PIPELINE})"; API_SEV="ok" ;;
    2) API_STATUS="starting (not yet ready)";                     API_SEV="warn" ;;
    *) API_STATUS="not started";                                 API_SEV="warn" ;;
  esac
fi

if [ "$WANT_WEB" = "1" ]; then
  CURRENT=$((CURRENT + 1))
  ui::step "$CURRENT" "$STEPS" "web (Vite prerequisite-graph explorer)"
  web_rc=0
  start_web || web_rc=$?
  case "$web_rc" in
    0) WEB_STATUS="http://localhost:${WEB_PORT}";  WEB_SEV="ok" ;;
    2) WEB_STATUS="starting (not yet ready)";      WEB_SEV="warn" ;;
    *) WEB_STATUS="not started";                   WEB_SEV="warn" ;;
  esac
fi

# --- Start path: summary ----------------------------------------------------

ui::summary_begin "Startup Summary"
ui::summary_row "supabase" "$SUPABASE_STATUS" "$SUPABASE_SEV"
ui::summary_row "api"      "$API_STATUS"      "$API_SEV"
ui::summary_row "web"      "$WEB_STATUS"      "$WEB_SEV"
ui::summary_end

if [ "$WANT_WEB" = "1" ] && [ "$WEB_SEV" = "ok" ]; then
  printf "  %sOpen %shttp://localhost:%s%s — enter a topic and watch Lunaris build the course.%s\n" \
    "${UI_DIM}" "${UI_PRIMARY}" "${WEB_PORT}" "${UI_DIM}" "${UI_RESET}"
fi
printf "  %sLogs: %s.run-state/*.log%s · tear down with '%smake stop%s'.%s\n\n" \
  "${UI_DIM}" "${UI_PRIMARY}" "${UI_DIM}" "${UI_PRIMARY}" "${UI_DIM}" "${UI_RESET}"
