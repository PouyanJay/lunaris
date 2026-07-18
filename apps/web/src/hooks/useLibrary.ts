import { useCallback, useEffect, useRef, useState } from "react";

import { getLibraryCache, setLibraryCache } from "./libraryCache";
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
 * lands state after the component is gone or a newer load started.
 *
 * Stale-while-revalidate across navigation: a mount (or reload) shows the module-cached grid
 * immediately when one exists and revalidates in the background — the skeleton only appears on the
 * very first load of the session. A background-refresh failure keeps the cached cards rather than
 * blanking to an error.
 */
export function useLibrary(apiBaseUrl: string): LibraryFeed {
  const [state, setState] = useState<LibraryState>(() => {
    const cached = getLibraryCache();
    return cached ? { status: "ready", courses: cached } : { status: "loading" };
  });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    // Show the cache immediately (no skeleton) when we have one; only a cold session loads blank.
    const cached = getLibraryCache();
    setState(cached ? { status: "ready", courses: cached } : { status: "loading" });

    fetchCourseSummaries(apiBaseUrl, controller.signal)
      .then((courses) => {
        if (controller.signal.aborted) return;
        setLibraryCache(courses);
        setState({ status: "ready", courses });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof LibraryError ? error.message : "Couldn't load your courses.";
        // A background-refresh failure keeps the cached cards rather than blanking to an error.
        setState((prev) => (prev.status === "ready" ? prev : { status: "error", message }));
      });
  }, [apiBaseUrl]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
