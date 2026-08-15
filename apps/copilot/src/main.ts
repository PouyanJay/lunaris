import "./telemetry.js";

import { createServer } from "node:http";

import { SIM_REGISTRY_PATH } from "./contract.js";
import { liveListener } from "./endpoint.js";
import { handleSimRegistryRequest, simRegistryUrl } from "./simRegistry.js";

/** One JSON object per line, matching the Python side's structlog output, so all three runtimes'
 *  logs can be filtered on the same keys.
 *
 *  Takes the level rather than hardcoding `"info"`: the boot-failure path is the single most
 *  operationally important line this file emits, and a helper it could not use is a helper it would
 *  drift away from. */
function log(level: "info" | "error", event: string, fields: Record<string, unknown> = {}): void {
  const line = JSON.stringify({ level, event, ...fields });
  if (level === "error") {
    console.error(line);
  } else {
    console.log(line);
  }
}

/** How long a shutdown may wait for in-flight runs before giving up.
 *
 *  This service holds an SSE stream open for the length of a tutoring turn, and `server.close()`
 *  waits for every open connection to end. Without a deadline, one stuck turn blocks exit until the
 *  platform's SIGKILL — losing the clean-shutdown log line for the very event you would want to read
 *  afterwards. Long enough to let a normal turn finish, short enough to stay inside ACA's grace. */
const SHUTDOWN_GRACE_MS = 10_000;

/** Where the Python API lives. Required — there is no sensible default for a service whose entire
 *  job is to forward somewhere, and a wrong guess would fail at the first learner's run rather than
 *  at boot, where an operator is actually looking. */
const apiBaseUrl = process.env.LUNARIS_API_URL;

/** Which origins may call this runtime. Comma-separated, and empty means none: a runtime that
 *  defaulted to allowing every origin would let any page drive a learner's session with a token it
 *  had obtained by other means. */
const allowedOrigins = (process.env.LUNARIS_COPILOT_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

/** Whether this deployment registers Tier 3 simulators, matching the API's own `LUNARIS_LIVE_SIMS`.
 *
 *  Off unless asked for, and deliberately the same switch on both sides: the only simulator that
 *  exists is a placeholder, and a runtime advertising one the API will not mount — or the reverse —
 *  is two halves of a socket disagreeing about whether it is plugged in. */
const simsEnabled = (process.env.LUNARIS_LIVE_SIMS ?? "").trim().toLowerCase() === "stub";

const port = Number(process.env.PORT ?? 8100);

if (!apiBaseUrl) {
  log("error", "copilot.boot_failed", { reason: "LUNARIS_API_URL is not set" });
  process.exit(1);
}

// Validated rather than trusted: `Number("http://…")` is NaN, and `listen(NaN)` binds a random port
// instead of failing — so a typo'd PORT would produce a healthy-looking service nothing can reach.
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  log("error", "copilot.boot_failed", { reason: "PORT is not a valid port", port: process.env.PORT });
  process.exit(1);
}

const copilot = liveListener({
  apiBaseUrl,
  allowedOrigins,
  // Resolved after the port is validated, because the registry URL contains it.
  ...(simsEnabled ? { simRegistryUrl: simRegistryUrl(port) } : {}),
});

const server = createServer((request, response) => {
  // Answered here rather than through the runtime: a liveness probe must not depend on the
  // runtime's routing, or a broken route reads as a dead container and vice versa.
  if (request.url === "/healthz") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  // The Tier 3 registry, spoken to by the MCP Apps middleware in this same process. Served here
  // rather than through the CopilotKit runtime because it is not a CopilotKit route — it is an MCP
  // server that happens to live at the same address.
  if (simsEnabled && request.url?.startsWith(SIM_REGISTRY_PATH)) {
    void handleSimRegistryRequest(request, response, apiBaseUrl).catch((error: unknown) => {
      log("error", "copilot.sim_registry_failed", { message: String(error) });
      if (!response.headersSent) {
        response.writeHead(500, { "content-type": "application/json" });
      }
      response.end(JSON.stringify({ error: "sim registry failed" }));
    });
    return;
  }
  void copilot(request, response);
});

// Without this, a bind failure — two replicas racing for a port, most plausibly — surfaces as an
// unhandled exception and a raw stack trace, which is the one shape the rest of this file avoids.
server.on("error", (error: NodeJS.ErrnoException) => {
  log("error", "copilot.server_error", { code: error.code, message: error.message, port });
  process.exit(1);
});

server.listen(port, () => {
  log("info", "copilot.listening", {
    port,
    api_base_url: apiBaseUrl,
    allowed_origins: allowedOrigins,
    sim_registry: simsEnabled ? SIM_REGISTRY_PATH : null,
  });
});

// ACA sends SIGTERM on scale-in. Closing the server lets in-flight runs finish rather than cutting
// a learner off mid-sentence — but bounded, so a stuck turn cannot hold the process open forever.
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    log("info", "copilot.shutting_down", { signal, grace_ms: SHUTDOWN_GRACE_MS });
    const giveUp = setTimeout(() => {
      log("error", "copilot.shutdown_timed_out", { signal, grace_ms: SHUTDOWN_GRACE_MS });
      process.exit(1);
    }, SHUTDOWN_GRACE_MS);
    // `unref` so a shutdown that finishes early is not held open by its own deadline.
    giveUp.unref();
    server.close(() => {
      clearTimeout(giveUp);
      process.exit(0);
    });
  });
}
