import { HttpAgent } from "@ag-ui/client";

import { SESSION_HEADER } from "./contract.js";

/** The learner's bearer token, forwarded untouched.
 *
 *  This runtime terminates no auth of its own. It must not: FastAPI already verifies the Supabase
 *  JWT and scopes every session read to its owner, and a hop that authenticated *itself* to the API
 *  would become a way to reach any learner's session without their token. */
const AUTHORIZATION_HEADER = "authorization";

export class MissingSessionError extends Error {
  constructor() {
    super(`a run must name its session in the ${SESSION_HEADER} header`);
    this.name = "MissingSessionError";
  }
}

/** The AG-UI agent for one request: an HTTP hop onto this session's stream in the Python API.
 *
 *  Built per request rather than once at boot, because the URL names the session and the headers
 *  carry the caller's own token. A single long-lived agent would either serve every learner the
 *  same session or serve one learner's session with another's credentials.
 *
 *  No business logic lives here or anywhere else in this service (R2). Which move to make, what to
 *  teach, how to grade it: all of that stays behind this URL. What this hop adds is the middleware
 *  that only exists on this side of the wire — A2UI for Tier 2, MCP Apps for Tier 3. */
export function liveAgentFor(request: Request, apiBaseUrl: string): HttpAgent {
  const sessionId = request.headers.get(SESSION_HEADER);
  if (!sessionId) {
    throw new MissingSessionError();
  }

  const authorization = request.headers.get(AUTHORIZATION_HEADER);
  return new HttpAgent({
    url: `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/agui`,
    headers: authorization ? { [AUTHORIZATION_HEADER]: authorization } : {},
  });
}
