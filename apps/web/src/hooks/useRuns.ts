import { useCallback, useEffect, useRef, useState } from "react";

import { fetchRuns, RunsError } from "../lib/runs";
import type { CourseRun } from "../types/course";

export type RunsState =
  | { status: "loading" }
  | { status: "ready"; runs: CourseRun[] }
  | { status: "error"; message: string };

interface RunsFeed {
  state: RunsState;
  /** Re-fetch the run history (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Loads the sidebar's run history: loading → ready (the recent runs) or error. Each load aborts
 * any prior in-flight request, and the controller is aborted on unmount, so a slow fetch never
 * lands state after the component is gone or a newer load started.
 */
export function useRuns(apiBaseUrl: string): RunsFeed {
  const [state, setState] = useState<RunsState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    // Stale-while-revalidate: keep already-loaded runs visible while refreshing — only the very
    // first load shows the skeleton, so a post-build refresh doesn't blank the list.
    setState((prev) => (prev.status === "ready" ? prev : { status: "loading" }));

    fetchRuns(apiBaseUrl, controller.signal)
      .then((runs) => {
        if (!controller.signal.aborted) setState({ status: "ready", runs });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof RunsError ? error.message : "Couldn't load the run history.";
        // A background-refresh failure keeps the stale list rather than blanking it to an error.
        setState((prev) => (prev.status === "ready" ? prev : { status: "error", message }));
      });
  }, [apiBaseUrl]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
