import { useCallback, useEffect, useState } from "react";

import { loadGraph, type ConceptGraph } from "../lib/liveGraph";

/** A map read's data states. One read, so no progress: a map the learner already has is a row,
 *  not a compile — the compile now happens behind a session (P2c), where no one watches it. */
export type LiveGraphState =
  | { status: "loading" }
  | { status: "ready"; graph: ConceptGraph }
  | { status: "failed"; message: string };

export interface LiveGraphResult {
  state: LiveGraphState;
  /** Read the map again, after a failure. */
  retry: () => void;
}

/** Reads the map `graphId` names and tracks the read. Extracted from the shell so the surface stays
 *  a rendering concern; an in-flight read is abandoned when the id changes or the surface unmounts,
 *  and an abandoned read is the learner moving on rather than a failure. */
export function useLiveGraph(apiBaseUrl: string, graphId: string): LiveGraphResult {
  const [state, setState] = useState<LiveGraphState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    loadGraph(apiBaseUrl, graphId, controller.signal)
      .then((graph) => {
        if (!controller.signal.aborted) setState({ status: "ready", graph });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "failed",
          message: error instanceof Error ? error.message : "Couldn't open the map.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl, graphId, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, retry };
}
