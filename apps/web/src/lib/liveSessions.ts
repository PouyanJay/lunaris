import { authedFetch } from "./apiClient";
import { detailOf } from "./apiErrors";

/** Where a session is in its life. Mirrors `SessionStatus` server-side, and the set is closed for
 *  the same reason it is there: every surface is forced to notice a new one. */
export type LiveSessionStatus = "placing" | "warming" | "active" | "closed";

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
