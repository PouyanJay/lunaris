import { describe, expect, it } from "vitest";

import { BASE_PATH, LIVE_AGENT, SESSION_HEADER } from "../src/contract.js";

/** The three strings the browser and this service must agree on, asserted as *literals*.
 *
 *  They live in two separately deployed codebases — `apps/web/src/lib/copilotRuntime.ts` builds the
 *  URL and sets the header, this service mounts the route and reads it — so nothing at build time
 *  can catch them drifting apart. The symptom of a drift is a 404 on every run in production, with
 *  both sides individually passing their own tests.
 *
 *  Written against hardcoded strings on purpose. Mutation testing caught the alternative: the
 *  endpoint suite derived its request URL from `BASE_PATH`, so changing `BASE_PATH` to `/api/wrong`
 *  left the whole suite green — the test moved with the value it was supposed to pin.
 */
describe("the contract with apps/web", () => {
  it("mounts where the browser looks", () => {
    // apps/web: copilotRuntimeUrl() returns `${host}/api/copilotkit`
    expect(BASE_PATH).toBe("/api/copilotkit");
  });

  it("reads the header the browser sets", () => {
    // apps/web: sessionHeaders() returns { "x-lunaris-session-id": … }
    expect(SESSION_HEADER).toBe("x-lunaris-session-id");
  });

  it("exposes the agent the browser asks for", () => {
    // apps/web: <CopilotKit agent={LIVE_AGENT}> with LIVE_AGENT = "live"
    expect(LIVE_AGENT).toBe("live");
  });
});
