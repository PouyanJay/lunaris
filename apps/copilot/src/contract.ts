/** The vocabulary this service and `apps/web` must agree on.
 *
 *  One module, because the three of them are one thing: how a browser addresses this runtime. They
 *  were split across `endpoint.ts` and `liveAgent.ts` while `contract.test.ts` already treated them
 *  as a unit — and if they ever move into a shared package (a question T5 will face once the A2UI
 *  catalog adds to this same surface), it becomes a one-file move rather than a hunt.
 *
 *  Duplicated on purpose in `apps/web/src/lib/copilotRuntime.ts` rather than imported: the two are
 *  **separately deployed** Azure Container Apps, so a shared constant would only guarantee agreement
 *  at commit time and says nothing about which build is actually running where. `contract.test.ts`
 *  pins these as literals on this side and the web suite pins the same literals on its side, which
 *  is the part a shared import cannot do.
 */

/** Where this runtime answers. The SPA points `CopilotKit` at exactly this path. */
export const BASE_PATH = "/api/copilotkit";

/** Which agent the runtime exposes. One, because there is one loop. */
export const LIVE_AGENT = "live";

/** Which session a run belongs to, carried as a header.
 *
 *  The session id has to reach this hop somehow, and a header is the one place that works for both
 *  callers: CopilotKit owns the request *body* (it is an AG-UI `RunAgentInput`), so a field added
 *  there would be stripped or refused by the client's own schema. */
export const SESSION_HEADER = "x-lunaris-session-id";
