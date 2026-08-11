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
  });

  return createCopilotNodeListener({
    runtime,
    basePath: BASE_PATH,
    cors: {
      origin: [...config.allowedOrigins],
      // The learner's bearer token and the session id both ride custom headers, so a preflight
      // that does not allow them fails before the run is ever attempted.
      allowHeaders: ["content-type", "authorization", SESSION_HEADER],
    },
  });
}
