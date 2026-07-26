import { useCallback, useEffect, useRef, useState } from "react";

import { CostError, fetchCourseCostEvents } from "../lib/cost";
import type { CostEvent } from "../lib/cost";

export type CourseCostEventsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; events: CostEvent[] }
  | { status: "error"; message: string };

interface UseCourseCostEventsResult {
  state: CourseCostEventsState;
  /** Re-fetch the ledger (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Lazily loads a course's cost ledger for the drill-through — only once `enabled` (the panel is
 * expanded), so an unopened panel never fetches the full ledger. Stays `idle` until then; each load
 * aborts any prior in-flight request and the controller is aborted on unmount.
 */
export function useCourseCostEvents(
  apiBaseUrl: string,
  courseId: string,
  enabled: boolean,
): UseCourseCostEventsResult {
  const [state, setState] = useState<CourseCostEventsState>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    if (!apiBaseUrl || !enabled) {
      setState({ status: "idle" });
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchCourseCostEvents(apiBaseUrl, courseId, controller.signal)
      .then((events) => {
        if (!controller.signal.aborted) setState({ status: "ready", events });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CostError ? error.message : "Couldn't load the cost breakdown.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl, courseId, enabled]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
