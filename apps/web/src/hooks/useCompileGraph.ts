import { useCallback, useEffect, useRef, useState } from "react";

import { loadGraph, type ConceptGraph } from "../lib/liveGraph";
import { streamGraph, type CompileProgress } from "../lib/streamGraph";

/** The compile's data states. `idle` means there is nothing to compile — not that nothing happened
 *  yet — because Live cannot build a map without a topic.
 *
 *  `progress` is null until the compiler reports its first beat: a surface must be able to render
 *  the gap between asking and the first word back. */
export type CompileState =
  | { status: "idle" }
  | { status: "compiling"; progress: CompileProgress | null }
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
 *  unmounts, and an aborted compile is treated as the learner moving on rather than as a failure.
 *
 *  Streams rather than awaits: a cold compile runs for minutes, and the only surface that can be
 *  honest about that is one being told what the compiler is doing while it does it. */
export function useCompileGraph(apiBaseUrl: string, topic: string | undefined): CompileGraphResult {
  const [state, setState] = useState<CompileState>({ status: "idle" });
  // Bumped by `retry`, which re-runs the effect rather than duplicating the compile call.
  const [attempt, setAttempt] = useState(0);
  // The id the server allocated for the last compile we asked for, learned from a header before any
  // frame. Held in a ref rather than in state because reading it must never re-run the effect.
  const lastGraphId = useRef<string | null>(null);

  useEffect(() => {
    if (!topic) {
      setState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "compiling", progress: null });

    // A stream that dropped did not stop the compile behind it: the server runs it to completion
    // and persists it under the id we were already given. So a retry reads that map first, and only
    // compiles again if it genuinely is not there — the difference between waiting one request and
    // waiting another three minutes for the same result.
    const resume = lastGraphId.current;
    const compile = () =>
      streamGraph(apiBaseUrl, topic, {
        signal: controller.signal,
        onGraphId: (graphId) => (lastGraphId.current = graphId),
        onProgress: (progress) => {
          // Guarded because a beat can land in the same tick as an abort: without this, a learner
          // who has already moved on would be pulled back to a compile they left.
          if (!controller.signal.aborted) setState({ status: "compiling", progress });
        },
      });

    const attempted = resume
      ? loadGraph(apiBaseUrl, resume, controller.signal).catch(() => compile())
      : compile();

    attempted
      .then((graph) => {
        if (!controller.signal.aborted) setState({ status: "ready", graph });
      })
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
