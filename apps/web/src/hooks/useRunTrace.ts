import { useCallback, useEffect, useRef, useState } from "react";

import { fetchRunEvents, RunsError } from "../lib/runs";
import { splitRunEvents } from "../lib/splitRunEvents";
import type { AgentEvent, ProgressEvent } from "../types/course";

export type RunTraceState =
  | { status: "loading" }
  // No persisted log: a course built before replay shipped, a run whose log writes failed, or one
  // opened without a run_id. Rendered as a "no build record" empty state, not an error.
  | { status: "empty" }
  | { status: "ready"; events: ProgressEvent[]; agentEvents: AgentEvent[] }
  | { status: "error"; message: string };

interface RunTrace {
  state: RunTraceState;
  /** Re-fetch the build log (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Loads a past run's persisted build log for static replay: loading → ready (the two timeline
 * streams) / empty (no record) / error. A missing `runId` resolves straight to empty (nothing to
 * fetch). Each load aborts any prior in-flight request, and the controller is aborted on unmount, so
 * a slow fetch never lands state after the view changed or a newer load started.
 */
export function useRunTrace(apiBaseUrl: string, runId: string | undefined): RunTrace {
  const [state, setState] = useState<RunTraceState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    if (!runId) {
      setState({ status: "empty" });
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchRunEvents(apiBaseUrl, runId, controller.signal)
      .then((rows) => {
        if (controller.signal.aborted) return;
        if (rows.length === 0) {
          setState({ status: "empty" });
          return;
        }
        setState({ status: "ready", ...splitRunEvents(rows) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof RunsError ? error.message : "Couldn't load this build record.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl, runId]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
