import "./telemetry.js";

import { CopilotRuntime } from "@copilotkit/runtime/v2";
import { createCopilotNodeListener } from "@copilotkit/runtime/v2/node";

import { BASE_PATH, LIVE_AGENT, SESSION_HEADER } from "./contract.js";
import { liveAgentFor } from "./liveAgent.js";

export interface EndpointConfig {
  /** Where the Python API lives, e.g. `http://localhost:8000`. */
  apiBaseUrl: string;
  /** Origins allowed to call this runtime — the SPA's, and nothing else. */
  allowedOrigins: readonly string[];
  /** Where this runtime's Tier 3 registry answers, or `undefined` for a deployment that registers
   *  no simulators. Undefined is the default and the honest one: the only simulator that exists is
   *  a placeholder, and there is nothing to register until Phase 3's factory has built something. */
  simRegistryUrl?: string | undefined;
}

/** Tier 3's registration, as the runtime takes it (T6).
 *
 *  Its own function so the decision is *observable*: whether the MCP Apps middleware is attached at
 *  all is a behavioural choice, and a test cannot see inside a constructed `CopilotRuntime`. Split
 *  out, the choice is a value a test can assert on rather than a claim in a comment.
 *
 *  Spread at the top level rather than nested under a `middlewares` key, which is how this runtime
 *  version takes them: `CopilotRuntimeOptions` *extends* `CopilotRuntimeMiddlewares`.
 *
 *  **Nothing at all when no registry is configured**, which is every deployment today. An empty
 *  server list still attaches the middleware, and an attached middleware wraps the event stream of
 *  every run — holding back `RUN_FINISHED` to look for tool calls that can never be there. That is
 *  a permanent cost on the critical path of every lesson in exchange for nothing, and Tier 3 is the
 *  one tier where nothing is exactly what is behind it so far. */
export function mcpAppsOptions(config: EndpointConfig): {
  mcpApps?: { servers: { url: string; type: "http" }[] };
} {
  if (!config.simRegistryUrl) {
    return {};
  }
  return { mcpApps: { servers: [{ url: config.simRegistryUrl, type: "http" }] } };
}

/** The CopilotKit runtime as a Node request listener.
 *
 *  `createCopilotNodeListener` rather than `createCopilotNodeHandler`: the latter takes a *fetch
 *  function*, and handing it the routed app it looks like it wants yields a 500 on every request.
 *  This is the process-owning entry point the runtime documents.
 *
 *  A listener rather than a `fetch` handler for tests, too, and that is deliberate. The runtime's
 *  SSE response enqueues strings, which Node's own `Response.text()` refuses ("Received
 *  non-Uint8Array chunk") — so an in-process `app.fetch(…)` test cannot read a stream that works
 *  perfectly over a socket. Exercising it through a real server tests the path production uses
 *  instead of one that only exists in the suite.
 *
 *  The agent is resolved **per request** from a factory. That is what lets one runtime serve every
 *  learner: the session id and the bearer token both arrive on the request, and neither can be
 *  baked into a boot-time singleton without leaking one learner's session to another. */
export function liveListener(config: EndpointConfig) {
  const runtime = new CopilotRuntime({
    agents: ({ request }) => ({ [LIVE_AGENT]: liveAgentFor(request, config.apiBaseUrl) }),
    ...mcpAppsOptions(config),
  });

  return createCopilotNodeListener({
    runtime,
    basePath: BASE_PATH,
    // The route shape, stated rather than defaulted: REST routes under the base path (`GET …/info`,
    // `POST …/agent/live/run`). The browser kit is told the same (`useSingleEndpoint={false}` in
    // apps/web); its *default* is the other shape, and the two 404 each other silently.
    mode: "multi-route",
    cors: {
      origin: [...config.allowedOrigins],
      // The learner's bearer token and the session id both ride custom headers, so a preflight
      // that does not allow them fails before the run is ever attempted.
      allowHeaders: ["content-type", "authorization", SESSION_HEADER],
    },
  });
}
