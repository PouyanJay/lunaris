import { describe, expect, it } from "vitest";

import { SESSION_HEADER } from "../src/contract.js";
import { MissingSessionError, liveAgentFor } from "../src/liveAgent.js";

/** A request as CopilotKit's client sends it to this hop. */
function runRequest(headers: Record<string, string>): Request {
  return new Request("http://runtime.test/api/copilotkit/agent/live/run", {
    method: "POST",
    headers,
  });
}

describe("the agent behind one run", () => {
  it("points at the session named in the request", () => {
    const agent = liveAgentFor(runRequest({ [SESSION_HEADER]: "sess-42" }), "http://api.test");

    expect(agent.url).toBe("http://api.test/api/live/sessions/sess-42/agui");
  });

  it("forwards the learner's own bearer token untouched", () => {
    // This hop must not authenticate as itself. FastAPI scopes every session read to its owner, so
    // a runtime holding its own credential would be a way to reach any learner's session.
    const agent = liveAgentFor(
      runRequest({ [SESSION_HEADER]: "sess-1", authorization: "Bearer learner-token" }),
      "http://api.test",
    );

    expect(agent.headers?.authorization).toBe("Bearer learner-token");
  });

  it("sends no authorization at all when the caller had none", () => {
    // Rather than an empty or placeholder credential, which the API would have to distinguish from
    // a real one. Absent means absent.
    const agent = liveAgentFor(runRequest({ [SESSION_HEADER]: "sess-1" }), "http://api.test");

    expect(agent.headers?.authorization).toBeUndefined();
  });

  it("escapes a session id rather than pasting it into the path", () => {
    // The id reaches this hop as a header from the browser. Interpolated raw, an id containing a
    // slash or a query character would address a different endpoint than the one intended.
    const agent = liveAgentFor(runRequest({ [SESSION_HEADER]: "a/../b?x=1" }), "http://api.test");

    expect(agent.url).toBe("http://api.test/api/live/sessions/a%2F..%2Fb%3Fx%3D1/agui");
  });

  it("refuses a run that names no session", () => {
    // Better than defaulting: a run with no session has nothing to teach, and inventing one would
    // open somebody's session from a request that never asked for it.
    expect(() => liveAgentFor(runRequest({}), "http://api.test")).toThrow(MissingSessionError);
  });
});
