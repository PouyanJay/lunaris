import type { VideoArtifact, VideoKind, VideoProvenance } from "../types/course";
import { authedFetch } from "./apiClient";

/** The job id to resolve a video artifact by: prefer the provenance jobId (the worker populates it
 *  on a READY artifact) over the artifact's own jobId (the coordinator stamps it even when FAILED).
 *  The single place that precedence lives — both the lesson hero and the course slot use it. */
export function resolveJobId(artifact: VideoArtifact | null | undefined): string | null {
  if (!artifact) return null;
  return artifact.provenance?.jobId ?? artifact.jobId ?? null;
}

export type VideoJobStatus =
  | "queued"
  | "planning"
  | "coding"
  | "rendering"
  | "qa"
  | "voicing"
  | "assembling"
  | "ready"
  | "failed"
  | "cancelled";

/** A determinate progress reading for a working video job: a percent (for the bar) and a plain-
 *  language stage label (for the caption). Mapped from the job status the worker advances through
 *  (planning → voicing? → rendering → assembling → ready); the percents rise monotonically so the
 *  bar only ever moves forward. The terminal `ready`/`failed` are included for completeness — the
 *  slot renders the player / failed message rather than this bar once a job settles. */
export function videoProgress(status: VideoJobStatus): { percent: number; label: string } {
  switch (status) {
    case "queued":
      return { percent: 6, label: "Queued" };
    case "planning":
      return { percent: 18, label: "Planning the storyboard" };
    case "coding":
      return { percent: 34, label: "Writing the animation" };
    case "voicing":
      return { percent: 46, label: "Recording the narration" };
    case "rendering":
      return { percent: 64, label: "Rendering the scenes" };
    case "qa":
      return { percent: 80, label: "Checking the visuals" };
    case "assembling":
      return { percent: 92, label: "Assembling the video" };
    case "ready":
      return { percent: 100, label: "Ready" };
    case "failed":
      return { percent: 100, label: "Couldn’t generate" };
    case "cancelled":
      return { percent: 100, label: "Stopped" };
  }
}

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
 *  playback URLs once it is ready, the grounding provenance once ready (the API sends it on a READY
 *  job — it carries the degraded-scene flags the reader surfaces), and whether the lesson it was
 *  built from has since been revised (`stale` — the reader's outdated badge, V6-T3). `captionsUrl`
 *  is present only for a narrated video. */
/** One navigable chapter of a ready video (Cinema): a scene with its span on the concatenated
 *  timeline, so a click can seek to exactly where the chapter begins. */
export interface VideoChapter {
  id: string;
  title: string;
  startS: number;
  endS: number;
}

/** One timed transcript cue of a ready video (Cinema): a spoken beat with its span, for a synced
 *  click-to-seek transcript. Absent for a silent (un-narrated) video. */
export interface TranscriptCue {
  startS: number;
  endS: number;
  text: string;
}

export interface VideoJobView {
  job: VideoJobWire;
  videoUrl: string | null;
  posterUrl: string | null;
  captionsUrl: string | null;
  provenance?: VideoProvenance | null;
  stale?: boolean;
  /** The Cinema outline of a ready video: navigable chapters + a timed transcript. Empty on a
   *  job that isn't ready or a video rendered before Cinema shipped. */
  chapters?: VideoChapter[];
  transcript?: TranscriptCue[];
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

/** The four regenerate-menu modes (V6-T2). RETRY / ADD_NARRATION reuse the prior contract (so they
 *  need a finished source); SIMPLER / FRESH re-plan. Mirrors the server enum. */
export type RegenerateMode = "retry" | "simpler" | "fresh" | "add_narration";

/** A failed video has no planned contract to reuse, so only the re-plan modes apply. */
export const FAILED_REGEN_MODES: RegenerateMode[] = ["fresh", "simpler"];

/** A finished video can reuse its contract; a silent one can also have narration added. */
export function readyRegenModes(captionsUrl: string | null): RegenerateMode[] {
  const modes: RegenerateMode[] = ["retry", "simpler", "fresh"];
  if (!captionsUrl) modes.push("add_narration");
  return modes;
}

/** How a regenerate attempt resolved. `conflict` = the reuse modes need a finished source (409);
 *  `disabled` = video turned off in Settings or the kill-switch (403/404); `error` = retryable. */
export type RegenerateResult =
  | { kind: "accepted"; view: VideoJobView }
  | { kind: "conflict"; detail: string }
  | { kind: "disabled" }
  | { kind: "error" };

/** Re-run a video through the regenerate menu (`POST /api/videos/{id}/regenerate`). The source job
 *  is identified by id; the server enqueues a new job entering the pipeline at the mode's node. */
export async function regenerateVideo(
  apiBaseUrl: string,
  jobId: string,
  mode: RegenerateMode,
): Promise<RegenerateResult> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/videos/${encodeURIComponent(jobId)}/regenerate`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode }),
      },
    );
  } catch {
    return { kind: "error" };
  }
  if (response.status === 403 || response.status === 404) return { kind: "disabled" };
  if (response.status === 409) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    return { kind: "conflict", detail: body?.detail ?? "This video hasn't finished yet." };
  }
  if (!response.ok) return { kind: "error" };
  return { kind: "accepted", view: (await response.json()) as VideoJobView };
}

/** The slot's live video job keyed by its COORDINATES (course, lesson, kind) — NOT a source job id.
 *  This is the derive-at-read probe: it resolves a slot whose course payload pointer is null OR
 *  FAILED-with-a-job-that-has-since-gone-READY (the async-after-delivery case — the cloud worker
 *  finishes a video minutes after the build delivered the course with a FAILED pointer, and nothing
 *  rewrites it). Returns the slot's in-flight job (else its latest finished render), or null when the
 *  slot has neither (204) / it can't be read. `lessonId` is omitted for course-level slots. */
export async function findActiveVideoJobByCoordinates(
  apiBaseUrl: string,
  courseId: string,
  kind: VideoKind,
  lessonId?: string | null,
  signal?: AbortSignal,
): Promise<VideoJobView | null> {
  const params = new URLSearchParams({ kind });
  if (lessonId) params.set("lessonId", lessonId);
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/videos/active?${params}`,
      signal ? { signal } : undefined,
    );
    if (response.status === 204 || !response.ok) return null;
    return (await response.json()) as VideoJobView;
  } catch {
    return null;
  }
}

/** One video job's lean status as the build canvas reads it (`GET /api/courses/{id}/videos`): the
 *  slot coordinates + status, enough to compute "N of M ready" without the full job/config payload. */
export interface CourseVideoStatusWire {
  jobId: string;
  kind: VideoKind;
  lessonId: string | null;
  status: VideoJobStatus;
}

/** The lean per-job status of EVERY video a course enqueued — drives the build canvas's "Videos N/M"
 *  phase after the build run completes (the videos render async, minutes after delivery). An empty
 *  array for a course that built no videos; null when it can't be read (network / unauthorized) so
 *  the caller keeps its last reading and retries on the next poll. */
export async function fetchCourseVideoStatuses(
  apiBaseUrl: string,
  courseId: string,
  signal?: AbortSignal,
): Promise<CourseVideoStatusWire[] | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/videos`,
      signal ? { signal } : undefined,
    );
    if (!response.ok) return null;
    return (await response.json()) as CourseVideoStatusWire[];
  } catch {
    return null;
  }
}

/** Re-mint a ready job's short-lived signed playback URLs — they expire ~1h after they resolve, so a
 *  reader who sits on the page then presses play loads a dead URL. Returns the fresh URL set while
 *  the job is still READY, or null when it can't be re-minted (gone / not playable) so the caller
 *  keeps what it has. Both the lesson hero and the course slot re-mint through this on a load error. */
export async function fetchFreshPlaybackUrls(
  apiBaseUrl: string,
  jobId: string,
): Promise<{
  videoUrl: string;
  posterUrl: string | null;
  captionsUrl: string | null;
  stale: boolean | undefined;
} | null> {
  const view = await fetchVideoJob(apiBaseUrl, jobId);
  if (!view?.videoUrl) return null;
  return {
    videoUrl: view.videoUrl,
    posterUrl: view.posterUrl,
    captionsUrl: view.captionsUrl,
    stale: view.stale,
  };
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

const TERMINAL: ReadonlySet<VideoJobStatus> = new Set(["ready", "failed", "cancelled"]);

/** Stop a video the caller owns (`POST /api/videos/{id}/cancel`) — a queued job is then never
 *  claimed, and an in-flight one is aborted by the worker (its render subprocess killed). Owner-
 *  scoped + idempotent on the server. Returns the job (now CANCELLED) so the reader can show the
 *  stopped state, or null when it can't be read (gone / unauthorized / network) — the caller still
 *  drops to its stopped state locally, since the stop request was sent. */
export async function cancelVideoJob(
  apiBaseUrl: string,
  jobId: string,
): Promise<VideoJobView | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/videos/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" },
    );
    if (!response.ok) return null;
    return (await response.json()) as VideoJobView;
  } catch {
    return null;
  }
}

/** Poll a job until it settles (`ready`/`failed`) or `signal` aborts: `onWorking` fires for each
 *  in-flight status, `onSettled` once for the terminal view. A missed read (null) is retried — a
 *  transient blip must not strand a slow job, and the abort is the intended stop. Shared by the
 *  on-demand hero and the course-video slot so both regenerate-and-watch identically. */
export async function pollVideoJob(
  apiBaseUrl: string,
  jobId: string,
  opts: {
    signal: AbortSignal;
    intervalMs: number;
    onWorking: (status: VideoJobStatus) => void;
    onSettled: (view: VideoJobView) => void;
  },
): Promise<void> {
  while (!opts.signal.aborted) {
    const view = await fetchVideoJob(apiBaseUrl, jobId, opts.signal);
    if (opts.signal.aborted) return;
    if (view === null) {
      await delay(opts.intervalMs, opts.signal);
      continue;
    }
    if (TERMINAL.has(view.job.status)) {
      opts.onSettled(view);
      return;
    }
    opts.onWorking(view.job.status);
    await delay(opts.intervalMs, opts.signal);
  }
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}
