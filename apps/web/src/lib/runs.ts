/** Run-history API client. Reads the recent course-build runs that feed the sidebar. */

import type { CourseRun } from "../types/course";

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
    response = await fetch(`${apiBaseUrl}/api/runs`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new RunsError("Could not reach the run history.", { cause });
  }
  if (!response.ok) {
    throw new RunsError(`Couldn't load the run history (HTTP ${response.status}).`);
  }
  return response.json() as Promise<CourseRun[]>;
}
