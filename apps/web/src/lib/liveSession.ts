import { authedFetch } from "./apiClient";
import { detailOf } from "./apiErrors";
import type { LayoutSpec } from "./layoutSpec";
import type { SurfaceSpec } from "./surfaceSpec";

/** The server's own bound on an answer, mirrored so the box can stop a learner writing past it
 *  rather than letting the request come back 422 with the words they typed. */
export const MAX_ANSWER_CHARS = 4000;

/** What the director decided to do next — the plan's four moves, plus `place`: the one a session
 *  makes while its map is still compiling (P2c), a question about the learner rather than a
 *  lesson about a concept. */
export type MoveKind = "introduce" | "retrieve" | "remediate" | "close" | "place";

/** One decision by the director, with the reasoning that produced it.
 *
 *  `reason` is not decoration: a session is dozens of choices made in seconds on the learner's
 *  behalf, and it is the only way to tell a good policy from a lucky one afterwards. */
export interface DirectorMove {
  kind: MoveKind;
  /** The concept this move is about; null only for `close` (about the session) and `place`
   *  (about the learner, before there are concepts). */
  nodeId: string | null;
  reason: string;
}

/** What one answer was judged to show, and why. Three verdicts and not a score: the grader marks
 *  one answer against one explicit do-statement, and a number would claim a precision it lacks. */
export interface TurnGrade {
  kind: "met" | "partial" | "not_met";
  reason: string;
}

/** The one thing the learner was asked to DO on this turn — the bar their answer is marked against.
 *  Copied onto the turn server-side, so a transcript cannot come to misreport what was asked. */
export interface StagedCriterion {
  kind: "predict" | "manipulate" | "explain";
  statement: string;
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
  /** What the learner was asked to demonstrate, or null when the concept has nothing a text
   *  session can check (its criteria need a simulator — Phase 3). */
  criterion: StagedCriterion | null;
  /** What they said. Null on the turn in front of them, which is what makes it the open one. */
  answer: string | null;
  /** What that answer was judged to show. Null when nothing was staged to judge it against. */
  grade: TurnGrade | null;
  /** The Tier 1 card this turn put on screen, and its props (P2b T3). Null on every turn stored
   *  before P2b, which is why it is optional rather than assumed — a surface that read it as
   *  required would fail on the whole of Live's own history. */
  surface: SurfaceSpec | null;
  /** How this turn was composed for this learner (P2b T5) — where the words and the card go, and
   *  what supporting material sits around them. Null on every turn stored before P2b, and on a turn
   *  whose material could not be written, which is why the renderer falls back to the words and the
   *  card rather than to nothing. */
  layout: LayoutSpec | null;
}

/** A learner's run at a concept graph. Persisted server-side, so a reload resumes it. */
export interface LiveSession {
  sessionId: string;
  /** The map this session walks — minted before the compile when the session opened on a topic,
   *  so a placing session already names the map it is waiting for. */
  graphId: string;
  /** What the session is about, when it opened on a topic (P2c). Absent on a session opened on a
   *  map, whose topic is the map's. */
  topic?: string | null;
  /** Who this learner is, as the placement interview put it (P2c T3): carried for the tutor,
   *  shown nowhere yet. Absent until placed. */
  profile?: string | null;
  /** `placing` is a session whose map is still compiling: the learner is being interviewed, not
   *  taught, and nothing is staged. `warming` is the honest wait after the interview has run out
   *  and before the map has landed: nothing to answer, the surface advances it (P2c). */
  status: "placing" | "warming" | "active" | "closed";
  /** When the session opened (ISO 8601, UTC). The session is bounded by wall time, so this is what
   *  a surface needs to show how much of it is left — and it survives a reload because it is on the
   *  row rather than in whichever process happened to serve the request. */
  startedAt: string;
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

/** The two ways a session opens (U1): on a map the learner already has, teaching from turn 1; or
 *  on a topic whose map does not exist yet, interviewing while it compiles (P2c). Exactly one, and
 *  the type says so — a request naming both or neither is refused at the door. */
export type SessionOpening =
  | { graphId: string; topic?: undefined }
  | { topic: string; graphId?: undefined };

/** Open a session. Resolves with the session already talking — its first lesson on a map, or the
 *  interviewer's first question on a topic — because an empty shell the surface then had to poll
 *  would be a loading spinner with a row behind it. */
export async function startSession(
  apiBaseUrl: string,
  opening: SessionOpening,
  signal?: AbortSignal,
): Promise<LiveSession> {
  // Only the named half goes out. `{ graphId: undefined, topic }` would serialise away the
  // undefined, but spelling it out is what keeps this true when someone adds a field.
  const body =
    opening.topic !== undefined ? { topic: opening.topic } : { graphId: opening.graphId };
  return request(
    apiBaseUrl,
    `${apiBaseUrl}/api/live/sessions`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      ...(signal ? { signal } : {}),
    },
    opening.topic !== undefined
      ? "Couldn't start a session on this topic."
      : "Couldn't start a session on this map.",
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

/** Answer the criterion the last turn staged. Resolves with the WHOLE session, not just the new
 *  turn: the answered turn changes too — it gains the learner's words and the verdict on them — and
 *  a surface stitching two shapes together is one that can disagree with the row behind it.
 *
 *  `answeringSeq` names the turn being answered, so a double-submit is refused (409) rather than
 *  graded against the question that replaced it. */
export async function answerTurn(
  apiBaseUrl: string,
  sessionId: string,
  answer: string,
  answeringSeq: number,
  signal?: AbortSignal,
): Promise<LiveSession> {
  return request(
    apiBaseUrl,
    `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/turns`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ answer, answeringSeq }),
      ...(signal ? { signal } : {}),
    },
    "Couldn't send that answer.",
  );
}

/** Move a warming session on, if its map has landed (P2c T2). Resolves with the session when there
 *  was something to do (teaching began, the session closed on a failed compile, or an answer got
 *  there first), and with `null` while it is still warming (202, no body): a distinct answer rather
 *  than an error, "ask again in a moment". */
export async function advanceSession(
  apiBaseUrl: string,
  sessionId: string,
  signal?: AbortSignal,
): Promise<LiveSession | null> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/advance`,
      { method: "POST", ...(signal ? { signal } : {}) },
    );
  } catch (cause) {
    throw new LiveSessionError("Could not reach the session.", { cause });
  }
  if (response.status === 202) return null;
  if (!response.ok) {
    throw new LiveSessionError(
      (await detailOf(response)) ?? `Couldn't move the session on. (HTTP ${response.status})`,
    );
  }
  const body: unknown = await response.json();
  if (!isSession(body)) {
    throw new LiveSessionError("Couldn't read the session (unexpected response).");
  }
  return body;
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
    (body.status === "placing" ||
      body.status === "warming" ||
      body.status === "active" ||
      body.status === "closed") &&
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
