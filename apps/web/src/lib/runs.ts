import { authedFetch } from "./apiClient";
/** Run-history API client. Reads the recent course-build runs that feed the sidebar, and a single
 *  run's persisted build-event log for replay. */

import type { CourseRun, RunEvent } from "../types/course";

export class RunsError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "RunsError";
  }
}

/** Fetch the recent build runs (newest first). Rejects with RunsError on a transport/HTTP failure
 *  so the caller can surface a recoverable message rather than a raw stack trace. */
export async function fetchRuns(apiBaseUrl: string, signal?: AbortSignal): Promise<CourseRun[]> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/runs`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new RunsError("Could not reach the run history.", { cause });
  }
  if (!response.ok) {
    throw new RunsError(`Couldn't load the run history (HTTP ${response.status}).`);
  }
  return response.json() as Promise<CourseRun[]>;
}

/** Fetch a run's persisted build-event log (ordered by seq) for timeline replay. An empty array is
 *  a valid result (a course built before this shipped, or one whose log writes failed) — the caller
 *  renders a "no build record" state. Rejects with RunsError on a transport/HTTP failure. */
export async function fetchRunEvents(
  apiBaseUrl: string,
  runId: string,
  signal?: AbortSignal,
): Promise<RunEvent[]> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/runs/${encodeURIComponent(runId)}/events`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new RunsError("Could not reach the build history.", { cause });
  }
  if (!response.ok) {
    throw new RunsError(`Couldn't load the build record (HTTP ${response.status}).`);
  }
  return response.json() as Promise<RunEvent[]>;
}
