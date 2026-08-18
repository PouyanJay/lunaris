import { HttpAgent } from "@ag-ui/client";
import type { BaseEvent, RunAgentInput } from "@ag-ui/client";
import { type Observable, catchError, throwError } from "rxjs";

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

/** What the HTTP client raises when the API answers a run with a status rather than a stream:
 *  `HTTP <status>: <body>`, with the parsed body on `payload`. Read structurally rather than by
 *  class, because the client mints a plain `Error` and decorates it. */
interface StatusError {
  status?: unknown;
  payload?: unknown;
}

/** The learner-facing sentence in a refusal, or `undefined` when the answer carried none.
 *
 *  FastAPI's `failure_mapping` puts every refusal's sentence under `detail`, the ceiling, a
 *  duplicate send, a stale answer, a closed session, and each sentence already says what to do
 *  next. Only that string is taken; a body of any other shape is left to the client's own text,
 *  which at least names the status. */
export function refusalSentence(error: unknown): string | undefined {
  const payload = (error as StatusError | null)?.payload;
  if (typeof payload !== "object" || payload === null) {
    return undefined;
  }
  const detail = (payload as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.length > 0 ? detail : undefined;
}

/** The API's own AG-UI stream, with a refusal relayed in the API's words (T9).
 *
 *  `HttpAgent` reports a non-2xx as an error whose message is `HTTP 429: {"detail":"…"}`, the
 *  status and the JSON envelope, verbatim, and the kit's runner turns whatever an agent throws
 *  into the `RUN_ERROR` the browser shows the learner. Left alone, a session that has reached its
 *  ceiling put a JSON object in the learner's alert. This unwraps the sentence and nothing else:
 *  which refusals exist and what they say stays behind the URL (R2). */
class LiveHttpAgent extends HttpAgent {
  override run(input: RunAgentInput): Observable<BaseEvent> {
    return super.run(input).pipe(
      catchError((error: unknown) => {
        const sentence = refusalSentence(error);
        if (sentence === undefined) {
          return throwError(() => error);
        }
        const refused = new Error(sentence);
        // Kept for anything upstream that reads the status off the error, as the client's own
        // callers may, the message is the only thing that changes.
        Object.assign(refused, { status: (error as StatusError).status, cause: error });
        return throwError(() => refused);
      }),
    );
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
  return new LiveHttpAgent({
    url: `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/agui`,
    headers: authorization ? { [AUTHORIZATION_HEADER]: authorization } : {},
  });
}
