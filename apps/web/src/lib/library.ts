import { authedFetch } from "./apiClient";

import type { CourseSummary } from "../types/course";

export class LibraryError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "LibraryError";
  }
}

/** Fetch the caller's course library (newest first). Rejects with LibraryError on a
 *  transport/HTTP failure so the caller can surface a recoverable message. */
export async function fetchCourseSummaries(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<CourseSummary[]> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/courses`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new LibraryError("Could not reach the course library.", { cause });
  }
  if (!response.ok) {
    throw new LibraryError(`Couldn't load your courses (HTTP ${response.status}).`);
  }
  return response.json() as Promise<CourseSummary[]>;
}
