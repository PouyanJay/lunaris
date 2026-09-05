import { authedFetch } from "./apiClient";
import type { LiveSessionStatus } from "./liveSession";
import { detailOf } from "./apiErrors";

/** Where a session is in its life. Re-exported from the session module rather than declared again:
 *  two hand-written copies of one wire enum is how the web came to reject a status the API had been
 *  sending for a week. */
export type { LiveSessionStatus } from "./liveSession";

/** One session as a list shows it: enough to recognise, far too little to resume from.
 *
 *  Deliberately not a trimmed `Session`. A session is read whole while it is being lived, because
 *  the transcript is the state; a learner looking over their sessions wants none of that, and
 *  twenty transcripts on the wire to draw twenty rows would be the wrong trade every way round. */
export interface LiveSessionSummary {
  sessionId: string;
  graphId: string;
  /** What the learner recognises it by. Null only for a map that carried no topic. */
  topic: string | null;
  status: LiveSessionStatus;
  turnCount: number;
  startedAt: string;
  /** When it last moved, which is what "newest first" means to a learner. */
  updatedAt: string;
}

export class LiveSessionsError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "LiveSessionsError";
  }
}

/** This learner's own sessions, newest first. Owner scoping is the server's, never a filter here:
 *  a list that trimmed other people's rows in the browser would have already been sent them. */
export async function loadSessions(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<LiveSessionSummary[]> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/live/sessions`, signal ? { signal } : {});
  } catch (cause) {
    throw new LiveSessionsError("Could not reach your sessions.", { cause });
  }
  if (!response.ok) {
    throw new LiveSessionsError(
      (await detailOf(response)) ?? `Couldn't read your sessions (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as LiveSessionSummary[];
}

export { isFinished } from "./liveSession";

/** Finish a session deliberately: the recap, the mastery delta, and the day to come back. */
export async function endSession(
  apiBaseUrl: string,
  sessionId: string,
): Promise<LiveSessionSummary | null> {
  return act(`${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/end`, "POST");
}

/** Leave a session without a ceremony. Not a delete: the transcript is still the learner's. */
export async function discardSession(apiBaseUrl: string, sessionId: string): Promise<null> {
  await act(`${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/discard`, "POST");
  return null;
}

/** Remove a session and its transcript. What the learner demonstrated survives (see below). */
export async function deleteSession(apiBaseUrl: string, sessionId: string): Promise<null> {
  await act(`${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}`, "DELETE");
  return null;
}

/** Forget what Lunaris concluded about this learner on one topic. The other half of the pair:
 *  deleting a session stops keeping what they said, this stops keeping what was concluded. */
export async function forgetTopic(apiBaseUrl: string, graphId: string): Promise<null> {
  await act(`${apiBaseUrl}/api/live/knowledge/${encodeURIComponent(graphId)}`, "DELETE");
  return null;
}

/** One verb against the session plane, with the API's own sentence when it refuses.
 *
 *  The refusals here are worth reading rather than swallowing: "a turn is in flight" and "you still
 *  have a session going on this topic" are both instructions, and a surface that replaced them with
 *  "something went wrong" would take the fix away from the learner. */
async function act(url: string, method: "POST" | "DELETE"): Promise<LiveSessionSummary | null> {
  let response: Response;
  try {
    response = await authedFetch(url, { method });
  } catch (cause) {
    throw new LiveSessionsError("Could not reach your sessions.", { cause });
  }
  if (!response.ok) {
    throw new LiveSessionsError(
      (await detailOf(response)) ?? `That didn't go through (HTTP ${response.status}).`,
    );
  }
  return response.status === 204 ? null : ((await response.json()) as LiveSessionSummary);
}
