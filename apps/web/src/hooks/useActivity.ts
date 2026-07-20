import { useCallback, useEffect, useRef, useState } from "react";

import { ActivityError, fetchActivity } from "../lib/activity";
import type { ActivityView } from "../lib/activity";

export type ActivityState =
  | { status: "loading" }
  | { status: "ready"; view: ActivityView }
  | { status: "error"; message: string };

interface UseActivityResult {
  state: ActivityState;
  /** Re-fetch the snapshot (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Loads the learner's activity snapshot: loading → ready or error. Each load aborts any prior
 * in-flight request, and the controller is aborted on unmount, so a slow fetch never lands state
 * after the component is gone or a newer load started. Stale-while-revalidate: a reload keeps the
 * loaded snapshot visible instead of blanking to the skeleton.
 */
export function useActivity(apiBaseUrl: string, enabled = true): UseActivityResult {
  const [state, setState] = useState<ActivityState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    // No origin (offline / no key), or the consumer doesn't need activity right now — settle
    // without a wasted fetch. Consumers treat a non-ready snapshot as "no activity" (streak 0,
    // the Trail band absent).
    if (!apiBaseUrl || !enabled) {
      setState({ status: "error", message: "Activity is unavailable." });
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((prev) => (prev.status === "ready" ? prev : { status: "loading" }));

    fetchActivity(apiBaseUrl, controller.signal)
      .then((view) => {
        if (!controller.signal.aborted) setState({ status: "ready", view });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ActivityError ? error.message : "Couldn't load your activity.";
        // A background-refresh failure keeps the stale snapshot rather than blanking to an error.
        setState((prev) => (prev.status === "ready" ? prev : { status: "error", message }));
      });
  }, [apiBaseUrl, enabled]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
