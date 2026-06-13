import { authedFetch } from "./apiClient";

export type VideoJobStatus =
  | "queued"
  | "planning"
  | "coding"
  | "rendering"
  | "qa"
  | "voicing"
  | "assembling"
  | "ready"
  | "failed";

export interface VideoJobWire {
  id: string;
  userId: string;
  courseId: string;
  lessonId: string | null;
  kind: "summary" | "overview" | "lesson";
  status: VideoJobStatus;
  error?: string | null;
}

/** The wire shape of `GET /api/videos/{id}` / the enqueue response: the job row plus signed
 *  playback URLs once it is ready. */
export interface VideoJobView {
  job: VideoJobWire;
  videoUrl: string | null;
  posterUrl: string | null;
}

/** How an enqueue attempt resolved — the three non-success shapes are product states, not
 *  errors: `keyless` (the Draft tier doesn't include videos), `unavailable` (the operator
 *  kill-switch is off → the surface doesn't exist), and `error` (network/5xx; retryable). */
export type EnqueueResult =
  | { kind: "accepted"; view: VideoJobView }
  | { kind: "keyless"; detail: string }
  | { kind: "unavailable" }
  | { kind: "error" };

export async function enqueueLessonVideo(
  apiBaseUrl: string,
  courseId: string,
  lessonId: string,
): Promise<EnqueueResult> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/lessons/${encodeURIComponent(lessonId)}/video`,
      { method: "POST" },
    );
  } catch {
    return { kind: "error" };
  }
  if (response.status === 404) return { kind: "unavailable" };
  if (response.status === 403) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    return {
      kind: "keyless",
      detail: body?.detail ?? "Video generation needs an Anthropic API key — add one in Settings.",
    };
  }
  if (!response.ok) return { kind: "error" };
  return { kind: "accepted", view: (await response.json()) as VideoJobView };
}

/** One job's current view, or null when it can't be read (gone, unauthorized, network). */
export async function fetchVideoJob(
  apiBaseUrl: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<VideoJobView | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/videos/${encodeURIComponent(jobId)}`,
      signal ? { signal } : undefined,
    );
    if (!response.ok) return null;
    return (await response.json()) as VideoJobView;
  } catch {
    return null;
  }
}
