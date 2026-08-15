import type { IncomingMessage, ServerResponse } from "node:http";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

import {
  SIM_REGISTRY_PATH,
  STUB_SIM_APP_ID,
  STUB_SIM_PATH,
  UI_RESOURCE_KEY,
} from "./contract.js";

/** The Tier 3 registry, as an MCP server (P2b T6).
 *
 *  Plan §8 says simulators are *"registered as MCP Apps so the host mounts them in place"*, and
 *  this is the smallest thing that makes that sentence true rather than aspirational: one server,
 *  one tool, and the tool carries a `uiResourceUri` (SEP-1865) pointing at a document a frame can
 *  load. `MCPAppsMiddleware` connects to it on each run and injects what it finds into the run's
 *  tool list, which is registration working end to end.
 *
 *  **What this is NOT is the evidence path, and that distinction is the whole design.** A learner
 *  working in a simulator has their report graded by the separate grader against the criterion the
 *  turn staged (U1) — over Lunaris's own answer path, in Python. Routing that through MCP instead
 *  would put the thing the learner model is built from inside a protocol hop that knows nothing
 *  about learners, and would commit Phase 3's sims to being MCP servers on the strength of a stub.
 *  So the two live side by side: MCP registers, Lunaris assesses.
 *
 *  **Co-located with the runtime on purpose.** A registry is a lookup, and the runtime is the only
 *  thing that reads it; a separate deployable would be a second thing to build, ship and page
 *  somebody about before a single real simulator exists. Phase 3 moves it out the day the factory
 *  has somewhere better to put it, and the middleware config is the only line that changes. */
export function simRegistryServer(apiBaseUrl: string): McpServer {
  const server = new McpServer({ name: "lunaris-live-sims", version: "0.1.0" });

  server.registerTool(
    "mount_placeholder_simulator",
    {
      title: "Placeholder simulator",
      description:
        "Mounts the Tier 3 placeholder. It simulates nothing; it exists so the socket a real " +
        "simulator plugs into can be exercised end to end.",
      inputSchema: {},
      // SEP-1865: the tool carries the UI resource a host mounts for it, under the key the
      // middleware actually reads. Absolute, because the browser resolves it and the browser is
      // not this process.
      //
      // The key is the whole registration. An earlier version used a plausible-looking name from a
      // different vendor's spec, and `MCPAppsMiddleware.fetchUITools()` simply returned nothing —
      // a tool the middleware does not recognise as an *app* is an ordinary tool, so registration
      // silently did nothing while this server's own responses looked perfect. That is why the
      // test beside this drives the real middleware rather than this server's wire format.
      _meta: { [UI_RESOURCE_KEY]: `${apiBaseUrl}${STUB_SIM_PATH}` },
    },
    async () => ({
      content: [{ type: "text" as const, text: `Mounted ${STUB_SIM_APP_ID}.` }],
    }),
  );

  return server;
}

/** Serve one MCP request. Stateless: each request gets its own transport and closes with it.
 *
 *  Stateless rather than session-bearing because there is nothing to remember. The middleware
 *  connects, lists tools and disconnects on every run, and a session map would be state whose only
 *  job is to be cleaned up — with a leak if it ever is not. */
export async function handleSimRegistryRequest(
  request: IncomingMessage,
  response: ServerResponse,
  apiBaseUrl: string,
): Promise<void> {
  // Two casts, both at this boundary and both for the same reason: the MCP SDK's declarations are
  // not written for `exactOptionalPropertyTypes`, which this project turns on. `sessionIdGenerator:
  // undefined` is the SDK's own documented way to ask for stateless mode, and its `Transport`
  // interface declares optional handlers as non-optional. Casting here keeps the strictness on for
  // every line we own rather than relaxing the compiler for the whole workspace to import a
  // third-party type.
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
  } as unknown as ConstructorParameters<typeof StreamableHTTPServerTransport>[0]);
  response.on("close", () => {
    void transport.close();
  });
  await simRegistryServer(apiBaseUrl).connect(
    transport as unknown as Parameters<McpServer["connect"]>[0],
  );
  await transport.handleRequest(request, response);
}

/** Where this runtime serves its registry, for the middleware pointed at it. */
export function simRegistryUrl(port: number): string {
  return `http://127.0.0.1:${port}${SIM_REGISTRY_PATH}`;
}
