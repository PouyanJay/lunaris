import { useCallback, useEffect, useState } from "react";

import { loadSessions, type LiveSessionSummary } from "../lib/liveSessions";

/** The list read's data states. Empty is a *loaded* state and not a failure: a learner who has
 *  never opened a session has an answer, and it is a different screen from one that broke. */
export type LiveSessionsState =
  | { status: "loading" }
  | { status: "ready"; sessions: LiveSessionSummary[] }
  | { status: "failed"; message: string };

export interface LiveSessionsResult {
  state: LiveSessionsState;
  /** Read the list again, after a failure or after a session has been acted on. */
  refresh: () => void;
}

/** Reads this learner's sessions and tracks the read. An in-flight read is abandoned when the
 *  surface unmounts, and an abandoned read is the learner moving on rather than a failure. */
export function useLiveSessions(apiBaseUrl: string): LiveSessionsResult {
  const [state, setState] = useState<LiveSessionsState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    loadSessions(apiBaseUrl, controller.signal)
      .then((sessions) => {
        if (!controller.signal.aborted) setState({ status: "ready", sessions });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "failed",
          message: error instanceof Error ? error.message : "Couldn't read your sessions.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl, attempt]);

  const refresh = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, refresh };
}
