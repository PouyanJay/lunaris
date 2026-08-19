import { useCallback, useEffect, useRef, useState } from "react";

import {
  answerTurn,
  loadSession,
  startSession,
  type LiveSession,
  type SessionOpening,
} from "../lib/liveSession";

/** A session's data states.
 *
 *  `answering` carries the session it is answering *within*: a send that fails must not take the
 *  transcript away from the learner, and a surface that dropped back to a bare error would lose
 *  everything they had read. `failed` carries it for the same reason — the last-known session is
 *  still theirs to read while the failure is explained. */
export type SessionState =
  | { status: "opening" }
  | { status: "ready"; session: LiveSession }
  | { status: "answering"; session: LiveSession }
  | { status: "failed"; message: string; session: LiveSession | null };

export interface LiveSessionResult {
  state: SessionState;
  /** Answer the turn in front of the learner. Ignored while one is already in flight. */
  answer: (text: string) => void;
  /** Re-open the session after a failure to start one. */
  retry: () => void;
  /** Re-read the session's row, for when something other than `answer` has moved it on: the
   *  generative panel taking a turn (T10). Ignored before there is a session to re-read. */
  refresh: () => void;
}

/** Opens a session — on a map the learner has, or on a topic (P2c) — and drives its loop.
 *
 *  Extracted from the surface so the view stays a rendering concern. The whole session comes back
 *  from every call — an answered turn changes as well as gaining a successor — so there is one
 *  shape here and no client-side stitching that could disagree with the row behind it. */
export function useLiveSession(apiBaseUrl: string, opening: SessionOpening): LiveSessionResult {
  const [state, setState] = useState<SessionState>({ status: "opening" });
  const [attempt, setAttempt] = useState(0);
  // Read inside `answer` without making it a dependency: re-creating the callback on every turn
  // would re-render the form and lose the caret mid-sentence.
  const current = useRef<SessionState>(state);
  current.current = state;
  // Keyed on what the opening NAMES, never on the object that names it: a caller passing a fresh
  // literal each render is the ordinary case, and an effect keyed on the object would open a new
  // session on every render of the surface. The object itself is read through a ref (the way
  // `current` is above), so the union reaches `startSession` intact rather than being rebuilt
  // from two loose strings.
  const { graphId, topic } = opening;
  const named = useRef<SessionOpening>(opening);
  named.current = opening;

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "opening" });
    startSession(apiBaseUrl, named.current, controller.signal)
      .then((session) => {
        if (!controller.signal.aborted) setState({ status: "ready", session });
      })
      .catch((error: unknown) => {
        // An abort is the learner moving on, not a failure to report at them.
        if (controller.signal.aborted) return;
        setState({ status: "failed", message: messageOf(error), session: null });
      });
    return () => controller.abort();
  }, [apiBaseUrl, graphId, topic, attempt]);

  const answer = useCallback(
    (text: string) => {
      const held = current.current;
      // Only from a settled session: a second send while one is in flight is the double-submit the
      // server refuses anyway, and refusing it here keeps the learner out of that round trip.
      if (held.status !== "ready" && held.status !== "failed") return;
      const session = held.session;
      if (!session || session.status === "closed") return;

      const asked = session.turns[session.turns.length - 1];
      if (!asked) return;

      setState({ status: "answering", session });
      answerTurn(apiBaseUrl, session.sessionId, text, asked.seq)
        .then((next) => setState({ status: "ready", session: next }))
        // The session they were reading stays on screen behind the message: a failed send is a
        // failed send, not a lost transcript.
        .catch((error: unknown) =>
          setState({ status: "failed", message: messageOf(error), session }),
        );
    },
    [apiBaseUrl],
  );

  const retry = useCallback(() => setAttempt((count) => count + 1), []);

  const refresh = useCallback(() => {
    const held = current.current;
    const session = held.status === "opening" ? null : held.session;
    if (!session) return;
    loadSession(apiBaseUrl, session.sessionId)
      .then((next) => setState({ status: "ready", session: next }))
      // A failed re-read leaves what was on screen: the record is stale rather than gone, and the
      // panel that caused the re-read is still the surface the learner is working in.
      .catch(() => {});
  }, [apiBaseUrl]);

  return { state, answer, retry, refresh };
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "The session could not continue.";
}
