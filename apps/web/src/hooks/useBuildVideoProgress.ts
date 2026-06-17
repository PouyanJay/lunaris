import { useEffect, useState } from "react";

import { fetchCourseVideoStatuses } from "../lib/videoJobs";

/** How often the build canvas re-reads the course's video jobs while they render. Matches the live
 *  run-trace cadence — videos take minutes on the cloud worker, so a few seconds is plenty. */
export const BUILD_VIDEO_PROGRESS_POLL_MS = 2500;

/** The build canvas's view of a course's async video generation: how many jobs there are, how many
 *  have finished (ready) / failed, and whether every job has settled (the canvas can advance). */
export interface BuildVideoProgress {
  total: number;
  ready: number;
  failed: number;
  /** Every job is terminal (ready or failed) — the videos phase is done. */
  settled: boolean;
}

/** Poll a just-built course's video jobs so the build canvas can show a "Videos N of M" phase after
 *  the run completes — the videos render async on the cloud worker, minutes after the build SSE has
 *  already ended (so the build stream can't carry their progress). Polls only while `active`, and
 *  stops once everything settles. Returns null until the first reading lands (and while inactive),
 *  so the caller can show a loading state; a missed read keeps the last reading and retries. */
export function useBuildVideoProgress(
  apiBaseUrl: string | undefined,
  courseId: string | undefined,
  active: boolean,
  pollIntervalMs: number = BUILD_VIDEO_PROGRESS_POLL_MS,
): BuildVideoProgress | null {
  const [progress, setProgress] = useState<BuildVideoProgress | null>(null);

  useEffect(() => {
    if (!active || !apiBaseUrl || !courseId) {
      setProgress(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      const rows = await fetchCourseVideoStatuses(apiBaseUrl, courseId, controller.signal);
      if (cancelled) return;
      if (rows !== null) {
        let ready = 0;
        let failed = 0;
        for (const row of rows) {
          if (row.status === "ready") ready += 1;
          else if (row.status === "failed") failed += 1;
        }
        const settled = rows.length > 0 && ready + failed === rows.length;
        setProgress({ total: rows.length, ready, failed, settled });
        if (settled) return; // everything terminal → stop polling (don't reschedule)
      }
      // Reschedule whether the read landed (unsettled) or missed (null) — a transient blip must not
      // strand the canvas; the next tick retries.
      timer = setTimeout(tick, pollIntervalMs);
    };

    void tick();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [active, apiBaseUrl, courseId, pollIntervalMs]);

  return progress;
}
