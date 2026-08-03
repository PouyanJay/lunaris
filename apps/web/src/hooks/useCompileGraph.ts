import { useCallback, useEffect, useState } from "react";

import { compileGraph, type ConceptGraph } from "../lib/liveGraph";

/** The compile's data states. `idle` means there is nothing to compile — not that nothing happened
 *  yet — because Live cannot build a map without a topic. */
export type CompileState =
  | { status: "idle" }
  | { status: "compiling" }
  | { status: "ready"; graph: ConceptGraph }
  | { status: "failed"; message: string };

export interface CompileGraphResult {
  state: CompileState;
  /** Re-run the compile for the same topic, after a failure. */
  retry: () => void;
}

/** Compiles `topic` into a concept map and tracks the attempt.
 *
 *  Extracted from the shell so the surface stays a rendering concern: this is where the compile
 *  lifecycle lives, and it is where the runtime graph extension (C1) will attach without the map's
 *  markup having to change. An in-flight compile is aborted when the topic changes or the surface
 *  unmounts, and an aborted compile is treated as the learner moving on rather than as a failure. */
export function useCompileGraph(apiBaseUrl: string, topic: string | undefined): CompileGraphResult {
  const [state, setState] = useState<CompileState>({ status: "idle" });
  // Bumped by `retry`, which re-runs the effect rather than duplicating the compile call.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!topic) {
      setState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "compiling" });
    compileGraph(apiBaseUrl, topic, controller.signal)
      .then((graph) => setState({ status: "ready", graph }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "failed",
          message: error instanceof Error ? error.message : "Couldn't build the map.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl, topic, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, retry };
}
