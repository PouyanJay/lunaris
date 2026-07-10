import type { CoverArtifact } from "../types/course";

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
