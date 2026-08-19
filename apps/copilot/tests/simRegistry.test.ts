import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it } from "vitest";

import { MCPAppsMiddleware } from "@ag-ui/mcp-apps-middleware";

import {
  SIM_REGISTRY_PATH,
  STUB_SIM_APP_ID,
  STUB_SIM_PATH,
  UI_RESOURCE_KEY,
} from "../src/contract.js";
import { liveListener, mcpAppsOptions } from "../src/endpoint.js";
import { handleSimRegistryRequest, simRegistryUrl } from "../src/simRegistry.js";

/** Tier 3's registration half (Phase 2b, T6).
 *
 *  Plan §8 says simulators are "registered as MCP Apps so the host mounts them in place". This is
 *  the part that makes that literal: an MCP server that advertises one UI-enabled tool, and a
 *  runtime configured to read it.
 *
 *  What is deliberately **not** here is the evidence path. A learner's work in a simulator is
 *  graded by Lunaris's own separate grader against the criterion the turn staged, over the answer
 *  path in Python — so nothing about a learner's mastery depends on any of this, which is exactly
 *  why the registry being unreachable is allowed to be a non-event (asserted below).
 *
 *  Driven over a real socket rather than in-process: the middleware speaks HTTP to the registry,
 *  and an in-process shortcut would test a path production does not have.
 */

const API_BASE = "http://api.test";

let running: Server | undefined;

afterEach(async () => {
  const server = running;
  running = undefined;
  if (server) {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

/** The registry on a real port, as the middleware reaches it. */
async function registryOnAPort(): Promise<string> {
  const server = createServer((request, response) => {
    void handleSimRegistryRequest(request, response, API_BASE);
  });
  running = server;
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  return simRegistryUrl((server.address() as AddressInfo).port);
}

/** One MCP call, spoken the way the middleware speaks it. */
async function mcp(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      // Both, because a streamable-HTTP server may answer either and refuses a client that
      // accepts neither.
      accept: "application/json, text/event-stream",
    },
    body: JSON.stringify(body),
  });
}

describe("registration, as the middleware actually performs it", () => {
  it("surfaces the simulator to MCPAppsMiddleware itself", async () => {
    // **The test the first version of this file was missing**, and the one that matters.
    //
    // Everything below drives our own server and asserts on its wire format, which proves we speak
    // valid MCP and nothing about whether registration *works*. It cannot: what makes a tool an
    // app is a `_meta` key the middleware looks for, and a tool carrying the wrong one is still a
    // perfectly valid tool — listed, returned, and never mounted. An earlier version of this
    // registry used a plausible key from another vendor's spec and `fetchUITools()` returned
    // nothing, with every assertion in this file still green.
    //
    // So this drives the real dependency instead of a description of it.
    const url = await registryOnAPort();
    const middleware = new MCPAppsMiddleware({ mcpServers: [{ type: "http", url }] });

    // `fetchUITools` is private on the class and the exported `MCPAppTool` type does not describe
    // what it returns, so the shape is taken from the value itself rather than from the
    // declaration — which is the point of driving the dependency instead of its types.
    const tools = await (
      middleware as unknown as {
        fetchUITools: () => Promise<{ tool: { name: string }; resourceUri: string }[]>;
      }
    ).fetchUITools();

    expect(tools.map((found) => found.tool.name)).toContain("mount_placeholder_simulator");
    expect(tools[0]?.resourceUri).toBe(`${API_BASE}${STUB_SIM_PATH}`);
  });
});

describe("the simulator registry", () => {
  it("advertises a simulator with somewhere for a frame to load it from", async () => {
    // SEP-1865: what makes a tool an *app* is that it carries a UI resource. A tool without one is
    // something an agent calls, not something a host mounts — so this is the whole registration.
    const url = await registryOnAPort();

    const initialised = await mcp(url, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "test", version: "0" },
      },
    });
    expect(initialised.status).toBe(200);

    const listed = await mcp(url, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    const body = await listed.text();

    expect(body).toContain("mount_placeholder_simulator");
    expect(body).toContain(`${API_BASE}${STUB_SIM_PATH}`);
  });

  it("points a host at the API's own document rather than at itself", async () => {
    // The registry says a simulator exists; the API serves it. Those are different services, and a
    // registry that served the document too would make Phase 3's factory have to publish through
    // this runtime instead of wherever it actually builds to.
    const url = await registryOnAPort();
    await mcp(url, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "test", version: "0" },
      },
    });

    const body = await (
      await mcp(url, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} })
    ).text();

    expect(body).toContain(API_BASE);
    expect(body).not.toContain(SIM_REGISTRY_PATH);
  });

  it("carries the key that makes a tool an app", () => {
    // Pinned as a literal beside the middleware test above, because this is the one thing about
    // registration that fails silently and in both directions.
    expect(UI_RESOURCE_KEY).toBe("ui/resourceUri");
  });

  it("names the same simulator the Python registry mints", () => {
    // A contract between two separately deployed things, pinned as a literal on both sides like
    // every other one in Live. `lunaris_live.session.stub_sim_registry` mints this id.
    expect(STUB_SIM_APP_ID).toBe("lunaris.sim.stub");
    expect(STUB_SIM_PATH).toBe("/api/live/sims/stub");
  });
});

describe("what a registry costs when it is not there", () => {
  it("attaches no middleware at all when no registry is configured", () => {
    // The default, and every deployment today. An empty server list would still attach it, and an
    // attached middleware wraps the event stream of every run — holding back `RUN_FINISHED` to look
    // for tool calls that cannot be there. A permanent cost on every lesson for nothing.
    expect(mcpAppsOptions({ apiBaseUrl: API_BASE, allowedOrigins: [] })).toEqual({});
    expect(() => liveListener({ apiBaseUrl: API_BASE, allowedOrigins: [] })).not.toThrow();
  });

  it("attaches it pointed at the registry when there is one", () => {
    const options = mcpAppsOptions({
      apiBaseUrl: API_BASE,
      allowedOrigins: [],
      simRegistryUrl: "http://127.0.0.1:9/mcp/sims",
    });

    expect(options).toEqual({
      mcpApps: { servers: [{ url: "http://127.0.0.1:9/mcp/sims", type: "http" }] },
    });
  });

  it("builds a runtime pointed at a registry that is not answering", () => {
    // The failure that matters operationally: the registry is decorative to a lesson, so a dead one
    // must not be able to take a turn down with it. Construction must not reach for it, and a run
    // that does is Lunaris's own answer path away from anything a learner depends on.
    expect(() =>
      liveListener({
        apiBaseUrl: API_BASE,
        allowedOrigins: [],
        simRegistryUrl: "http://127.0.0.1:1/mcp/sims",
      }),
    ).not.toThrow();
  });
});
