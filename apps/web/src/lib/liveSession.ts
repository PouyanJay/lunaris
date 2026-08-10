import { authedFetch } from "./apiClient";
import { detailOf } from "./apiErrors";

/** What the director decided to do next — the plan's four moves, and only these four. */
export type MoveKind = "introduce" | "retrieve" | "remediate" | "close";

/** One decision by the director, with the reasoning that produced it.
 *
 *  `reason` is not decoration: a session is dozens of choices made in seconds on the learner's
 *  behalf, and it is the only way to tell a good policy from a lucky one afterwards. */
export interface DirectorMove {
  kind: MoveKind;
  /** The concept this move is about; null only for `close`, which is about the session. */
  nodeId: string | null;
  reason: string;
}

/** One beat of the loop: what the director chose, and what the tutor said about it. */
export interface SessionTurn {
  /** 1-based, monotonic — the order the learner lived it. */
  seq: number;
  move: DirectorMove;
  tutor: string;
  /** The run that produced this turn — what a learner reporting a problem can name, and what ties
   *  a line of transcript to the model calls behind it. Not rendered; carried. */
  runId: string;
}

/** A learner's run at a concept graph. Persisted server-side, so a reload resumes it. */
export interface LiveSession {
  sessionId: string;
  graphId: string;
  status: "active" | "closed";
  turns: SessionTurn[];
}

/** Every way a session request can fail, as one error type — so the surface has one failure state
 *  to render rather than one per status and payload shape. */
export class LiveSessionError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "LiveSessionError";
  }
}

/** Open a session on a compiled map. Resolves with the session already teaching its first turn —
 *  an empty shell the surface then had to poll would be a loading spinner with a row behind it. */
export async function startSession(
  apiBaseUrl: string,
  graphId: string,
  signal?: AbortSignal,
): Promise<LiveSession> {
  return request(
    apiBaseUrl,
    `${apiBaseUrl}/api/live/sessions`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ graphId }),
      ...(signal ? { signal } : {}),
    },
    "Couldn't start a session on this map.",
  );
}

/** Re-read a session, so a reloaded tab lands back where the learner was. */
export async function loadSession(
  apiBaseUrl: string,
  sessionId: string,
  signal?: AbortSignal,
): Promise<LiveSession> {
  return request(
    apiBaseUrl,
    `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}`,
    signal ? { signal } : {},
    "Couldn't reopen that session.",
  );
}

async function request(
  _apiBaseUrl: string,
  url: string,
  init: RequestInit,
  fallback: string,
): Promise<LiveSession> {
  let response: Response;
  try {
    response = await authedFetch(url, init);
  } catch (cause) {
    throw new LiveSessionError("Could not reach the session.", { cause });
  }
  if (!response.ok) {
    // The server's own words where it has any — "map not found" and "storage is down" have
    // different next steps for the learner, and a status code has neither.
    throw new LiveSessionError(
      (await detailOf(response)) ?? `${fallback} (HTTP ${response.status})`,
    );
  }
  const body: unknown = await response.json();
  if (!isSession(body)) {
    throw new LiveSessionError("Couldn't read the session (unexpected response).");
  }
  return body;
}

/** Every field the surface reads, checked here so the view never has to. `turns` earns its place in
 *  particular: the transcript maps over it directly, so a payload missing it would throw a raw
 *  TypeError inside render rather than surfacing as the recoverable error this boundary promises. */
function isSession(payload: unknown): payload is LiveSession {
  const body = payload as LiveSession | null;
  return (
    !!body &&
    typeof body.sessionId === "string" &&
    typeof body.graphId === "string" &&
    (body.status === "active" || body.status === "closed") &&
    Array.isArray(body.turns) &&
    body.turns.every(
      (turn) =>
        typeof turn?.seq === "number" &&
        typeof turn?.tutor === "string" &&
        typeof turn?.move?.kind === "string" &&
        typeof turn?.move?.reason === "string",
    )
  );
}
