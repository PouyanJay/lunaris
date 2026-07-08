import { useEffect, useRef, useState } from "react";

import { fetchCourseSummaries } from "../lib/library";
import { fetchCourseById } from "../lib/loadCourse";
import { courseEntry, indexCourse } from "../lib/searchIndex";
import type { SearchEntry } from "../lib/searchIndex";

export type SearchIndexState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; entries: SearchEntry[] }
  | { status: "error"; message: string };

/**
 * The ⌘K palette's client-side index, built lazily on first open (plan decision: client-side now,
 * pgvector later): the library summaries give the course rows immediately; lessons/concepts need
 * each course's full payload, fetched in parallel. A course whose payload fails still contributes
 * its course row (Promise.allSettled) — partial truth beats a dead palette. Cached for the
 * session once built; `active=false` before the first open costs nothing.
 */
export function useSearchIndex(apiBaseUrl: string, active: boolean): SearchIndexState {
  const [state, setState] = useState<SearchIndexState>({ status: "idle" });
  const startedRef = useRef(false);

  useEffect(() => {
    if (!active || !apiBaseUrl || startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;
    setState({ status: "loading" });

    (async () => {
      const summaries = await fetchCourseSummaries(apiBaseUrl);
      const payloads = await Promise.allSettled(
        summaries.map((summary) => fetchCourseById(apiBaseUrl, summary.id)),
      );
      const entries: SearchEntry[] = summaries.map(courseEntry);
      for (const payload of payloads) {
        if (payload.status === "fulfilled") entries.push(...indexCourse(payload.value));
      }
      return entries;
    })()
      .then((entries) => {
        if (!cancelled) setState({ status: "ready", entries });
      })
      .catch(() => {
        if (cancelled) return;
        // Allow a retry on the next open — the failure was the summaries fetch itself.
        startedRef.current = false;
        setState({ status: "error", message: "Couldn't build the search index." });
      });

    return () => {
      cancelled = true;
    };
  }, [active, apiBaseUrl]);

  return state;
}
