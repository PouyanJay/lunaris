import { useCallback, useEffect, useRef, useState } from "react";

import { fetchCourseSummaries, LibraryError } from "../lib/library";
import type { CourseSummary } from "../types/course";

export type LibraryState =
  | { status: "loading" }
  | { status: "ready"; courses: CourseSummary[] }
  | { status: "error"; message: string };

interface LibraryFeed {
  state: LibraryState;
  /** Re-fetch the library (aborts any in-flight load first). */
  reload: () => void;
}

/**
 * Loads the My-courses library: loading → ready (the course summaries) or error. Each load aborts
 * any prior in-flight request, and the controller is aborted on unmount, so a slow fetch never
 * lands state after the component is gone or a newer load started. Stale-while-revalidate: a
 * reload keeps the loaded cards visible instead of blanking to the skeleton.
 */
export function useLibrary(apiBaseUrl: string): LibraryFeed {
  const [state, setState] = useState<LibraryState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((prev) => (prev.status === "ready" ? prev : { status: "loading" }));

    fetchCourseSummaries(apiBaseUrl, controller.signal)
      .then((courses) => {
        if (!controller.signal.aborted) setState({ status: "ready", courses });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof LibraryError ? error.message : "Couldn't load your courses.";
        // A background-refresh failure keeps the stale cards rather than blanking to an error.
        setState((prev) => (prev.status === "ready" ? prev : { status: "error", message }));
      });
  }, [apiBaseUrl]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
