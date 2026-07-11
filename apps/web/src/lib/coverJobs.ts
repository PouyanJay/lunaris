import type { CoverArtifact, CoverProvenance } from "../types/course";
import { authedFetch } from "./apiClient";

/** The cover-image job lifecycle — mirrors the runtime `CoverJobStatus`. There is exactly one cover
 *  per course, so (unlike video) there is no kind/lesson dimension. */
export type CoverJobStatus =
  | "queued"
  | "art_directing"
  | "rendering"
  | "qa"
  | "uploading"
  | "ready"
  | "failed"
  | "cancelled";

/** The art-direction preset a cover renders with — mirrors the runtime `CoverStylePreset`. Every
 *  preset keeps the locked anti-slop constraints; it varies the medium/mood, not the discipline. */
export type CoverStylePreset = "nocturne" | "blueprint" | "aurora";

/** The job id to resolve a cover artifact by: prefer the provenance jobId (populated on a READY
 *  artifact) over the artifact's own jobId (present even when FAILED). The single place that
 *  precedence lives, mirroring `resolveJobId` for video. */
export function resolveCoverJobId(artifact: CoverArtifact | null | undefined): string | null {
  if (!artifact) return null;
  return artifact.provenance?.jobId ?? artifact.jobId ?? null;
}

const TERMINAL: ReadonlySet<CoverJobStatus> = new Set(["ready", "failed", "cancelled"]);

/** Whether a cover job has settled (ready/failed/cancelled) — the reader stops polling once so. */
export function isCoverTerminal(status: CoverJobStatus): boolean {
  return TERMINAL.has(status);
}

/** A determinate progress reading for a working cover job: a percent (for the bar) and a plain-
 *  language stage label (for the caption). Mapped from the status the worker advances through
 *  (art_directing → rendering → qa → uploading → ready); the percents rise monotonically so the bar
 *  only ever moves forward. The terminal states are included for completeness — the slot renders the
 *  image / falls back rather than this bar once a job settles. */
export function coverProgress(status: CoverJobStatus): { percent: number; label: string } {
  switch (status) {
    case "queued":
      return { percent: 8, label: "Queued" };
    case "art_directing":
      return { percent: 30, label: "Art-directing the cover" };
    case "rendering":
      return { percent: 58, label: "Painting the image" };
    case "qa":
      return { percent: 78, label: "Checking the result" };
    case "uploading":
      return { percent: 92, label: "Finishing up" };
    case "ready":
      return { percent: 100, label: "Cover ready" };
    case "failed":
      return { percent: 100, label: "Cover generation failed" };
    case "cancelled":
      return { percent: 100, label: "Cover generation stopped" };
  }
}

/** One cover job as it rides on the wire (mirrors the runtime `CoverJob`) — the fields the reader
 *  needs off a `CoverJobView`. There is exactly one cover per course, so no kind/lesson dimension. */
export interface CoverJob {
  id: string;
  courseId: string;
  status: CoverJobStatus;
  stylePreset: CoverStylePreset;
  error?: string | null;
}

/** The `GET /api/covers/{jobId}` (and `/active`) response: the job row, a short-lived signed image
 *  URL once READY (never persisted stale — re-minted on demand), and the structural provenance. */
export interface CoverJobView {
  job: CoverJob;
  imageUrl?: string | null;
  provenance?: CoverProvenance | null;
}

/** One cover job's current view, or null when it can't be read (gone, unauthorized, network). The
 *  reader trades the READY view's `imageUrl` for the `<img>` src; a null is treated as "keep waiting"
 *  by the poller (a transient blip must not strand a slow job). */
export async function fetchCoverJob(
  apiBaseUrl: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<CoverJobView | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/covers/${encodeURIComponent(jobId)}`,
      signal ? { signal } : undefined,
    );
    if (!response.ok) return null;
    return (await response.json()) as CoverJobView;
  } catch {
    return null;
  }
}

/** Regenerate a course's cover (`POST /api/covers/{jobId}/regenerate`) — a fresh art-direction +
 *  render keyed by the source cover job. Keyed-gated + owner-scoped on the server; dedups an
 *  in-flight regenerate. Returns the (new or in-flight) job view, or null when it can't be read
 *  (gone / unauthorized / keyless-403 / network). */
export async function regenerateCover(
  apiBaseUrl: string,
  jobId: string,
): Promise<CoverJobView | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/covers/${encodeURIComponent(jobId)}/regenerate`,
      { method: "POST" },
    );
    if (!response.ok) return null;
    return (await response.json()) as CoverJobView;
  } catch {
    return null;
  }
}

/** Stop a cover the caller owns (`POST /api/covers/{jobId}/cancel`) — a queued job is then never
 *  claimed, an in-flight one aborted by the worker. Owner-scoped + idempotent on the server. Returns
 *  the job (now CANCELLED) or null when it can't be read; the caller drops to its stopped state
 *  regardless, since the stop request was sent. */
export async function cancelCover(apiBaseUrl: string, jobId: string): Promise<CoverJobView | null> {
  try {
    const response = await authedFetch(
      `${apiBaseUrl}/api/covers/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" },
    );
    if (!response.ok) return null;
    return (await response.json()) as CoverJobView;
  } catch {
    return null;
  }
}

/** Poll a cover job until it settles (`ready`/`failed`/`cancelled`) or `signal` aborts: `onWorking`
 *  fires for each in-flight status (drives the determinate caption), `onSettled` once for the
 *  terminal view. A missed read (null) is retried — a transient blip must not strand a slow job, and
 *  the abort is the intended stop. Mirrors `pollVideoJob`. */
export async function pollCoverJob(
  apiBaseUrl: string,
  jobId: string,
  opts: {
    signal: AbortSignal;
    intervalMs: number;
    onWorking: (status: CoverJobStatus) => void;
    onSettled: (view: CoverJobView) => void;
  },
): Promise<void> {
  while (!opts.signal.aborted) {
    const view = await fetchCoverJob(apiBaseUrl, jobId, opts.signal);
    if (opts.signal.aborted) return;
    if (view === null) {
      await coverDelay(opts.intervalMs, opts.signal);
      continue;
    }
    if (isCoverTerminal(view.job.status)) {
      opts.onSettled(view);
      return;
    }
    opts.onWorking(view.job.status);
    await coverDelay(opts.intervalMs, opts.signal);
  }
}

function coverDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
