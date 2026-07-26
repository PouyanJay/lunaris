import { useCallback, useEffect, useRef, useState } from "react";

import { CostError, fetchCourseCost } from "../lib/cost";
import type { CourseCost } from "../lib/cost";

export type CourseCostState =
  | { status: "loading" }
  /** `cost` is `null` when the course was never metered (built pre-feature or still building) —
   *  the panel renders that as a calm "not metered" note, distinct from an error. */
  | { status: "ready"; cost: CourseCost | null }
  | { status: "error"; message: string };

interface UseCourseCostResult {
  state: CourseCostState;
  /** Re-fetch the rollup (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Loads a course's build-cost rollup: loading → ready (with the rollup or `null` when unmetered) or
 * error. Each load aborts any prior in-flight request, and the controller is aborted on unmount, so
 * a slow fetch never lands state after the component is gone or a newer load started. An empty
 * `apiBaseUrl` (offline) settles as unmetered without a wasted fetch.
 */
export function useCourseCost(apiBaseUrl: string, courseId: string): UseCourseCostResult {
  const [state, setState] = useState<CourseCostState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    if (!apiBaseUrl) {
      setState({ status: "ready", cost: null });
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchCourseCost(apiBaseUrl, courseId, controller.signal)
      .then((cost) => {
        if (!controller.signal.aborted) setState({ status: "ready", cost });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CostError ? error.message : "Couldn't load this course's build cost.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl, courseId]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
