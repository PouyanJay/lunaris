import { authedFetch } from "./apiClient";
import type { BriefResponse } from "../types/clarifier";
import { CourseLoadError, isRecord } from "./loadCourse";

/**
 * Interpret a topic into a brief + the opt-in confirm clarifier (POST /api/briefs, P7.5 phase 1).
 * Network, HTTP, and malformed-payload failures all surface as {@link CourseLoadError} — one error
 * channel the Personalize panel renders as a retryable error state.
 */
export async function fetchBrief(
  apiBaseUrl: string,
  topic: string,
  signal?: AbortSignal,
): Promise<BriefResponse> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/briefs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic }),
      ...(signal ? { signal } : {}),
    });
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CourseLoadError(`Couldn't read your goal (HTTP ${response.status}).`, {
      status: response.status,
    });
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (cause) {
    throw new CourseLoadError("The brief response was not valid JSON.", { cause });
  }
  return parseBriefResponse(payload);
}

/** Shallow-validate the wire shape so the panel never renders from malformed data; the deep field
 *  types are trusted as the API's contract (the same posture as `parseCourse`). */
function parseBriefResponse(raw: unknown): BriefResponse {
  if (!isRecord(raw) || !isRecord(raw.brief) || !isRecord(raw.clarifier)) {
    throw new CourseLoadError("The brief response is missing its brief or clarifier.");
  }
  if (!Array.isArray(raw.clarifier.questions)) {
    throw new CourseLoadError("The clarifier is missing its questions.");
  }
  // Shape verified above; the schema is the API's contract.
  return raw as unknown as BriefResponse;
}
