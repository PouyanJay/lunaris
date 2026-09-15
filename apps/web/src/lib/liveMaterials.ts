/** Original timed source evidence; media access is resolved separately for the standing turn. */
export interface VideoClip {
  jobId: string;
  sourceDigest: string;
  locator: string;
  startS: number;
  endS: number;
  durationS: number;
  title: string;
  transcript: { startS: number; endS: number; text: string }[];
}
interface AssetVerification {
  runId: string;
  verifierVersion: string;
  sourceDigest: string;
}
/** Public source material contains no answer key or persistent media URL. */
export interface NodeAsset {
  assetId: string;
  kind: "lesson" | "assessment" | "video_clip";
  origin: "generated" | "ingested";
  locator: string;
  sourceDigest: string;
  title: string;
  excerpt: string;
  sourceLabel: string;
  verification: AssetVerification | null;
  clip: VideoClip | null;
}
const digest = /^[a-f0-9]{64}$/;
const locator = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/;
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function text(value: unknown, max: number, min = 0): value is string {
  return typeof value === "string" && value.length >= min && value.length <= max;
}
function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
function keys(value: Record<string, unknown>, names: string[]): boolean {
  return Object.keys(value).every((key) => names.includes(key));
}
function verification(value: unknown): value is AssetVerification {
  return (
    record(value) &&
    keys(value, ["runId", "verifierVersion", "sourceDigest"]) &&
    text(value.runId, 100, 1) &&
    text(value.verifierVersion, 100, 1) &&
    typeof value.sourceDigest === "string" &&
    digest.test(value.sourceDigest)
  );
}
function hasClipIdentity(value: Record<string, unknown>): boolean {
  return (
    text(value.jobId, 100, 1) &&
    /^[a-zA-Z0-9_-]+$/.test(value.jobId) &&
    typeof value.sourceDigest === "string" &&
    digest.test(value.sourceDigest) &&
    typeof value.locator === "string" &&
    /^video:[a-zA-Z0-9_-]+:[a-f0-9]{64}:[0-9]+:[0-9]+$/.test(value.locator) &&
    value.locator.startsWith(`video:${value.jobId}:${value.sourceDigest}:`) &&
    text(value.title, 300, 1)
  );
}
interface ClipInterval {
  startS: number;
  endS: number;
  durationS: number;
}
function hasClipInterval(
  value: Record<string, unknown>,
): value is Record<string, unknown> & ClipInterval {
  return (
    finite(value.startS) &&
    finite(value.endS) &&
    finite(value.durationS) &&
    value.startS >= 0 &&
    value.endS > value.startS &&
    value.endS - value.startS <= 90 &&
    value.endS <= value.durationS
  );
}
function hasClipTranscript(value: unknown, interval: ClipInterval): boolean {
  if (!Array.isArray(value) || value.length < 1 || value.length > 500) return false;
  let end = interval.startS;
  for (const cue of value) {
    if (
      !record(cue) ||
      !keys(cue, ["startS", "endS", "text"]) ||
      !finite(cue.startS) ||
      !finite(cue.endS) ||
      cue.startS < end ||
      cue.endS <= cue.startS ||
      cue.endS > interval.endS ||
      !text(cue.text, 10000, 1) ||
      !cue.text.trim()
    )
      return false;
    end = cue.endS;
  }
  return value[0].startS === interval.startS && end === interval.endS;
}
function isClip(value: unknown): value is VideoClip {
  return (
    record(value) &&
    keys(value, [
      "jobId",
      "sourceDigest",
      "locator",
      "startS",
      "endS",
      "durationS",
      "title",
      "transcript",
    ]) &&
    hasClipIdentity(value) &&
    hasClipInterval(value) &&
    hasClipTranscript(value.transcript, value)
  );
}
/** Validate the material boundary before any source text or media controls are rendered. */
export function isNodeAsset(value: unknown): value is NodeAsset {
  if (
    !record(value) ||
    !keys(value, [
      "assetId",
      "kind",
      "origin",
      "locator",
      "sourceDigest",
      "title",
      "excerpt",
      "sourceLabel",
      "verification",
      "clip",
    ])
  )
    return false;
  if (
    !text(value.assetId, 100, 1) ||
    typeof value.kind !== "string" ||
    !["lesson", "assessment", "video_clip"].includes(value.kind) ||
    typeof value.origin !== "string" ||
    !["generated", "ingested"].includes(value.origin) ||
    !text(value.locator, 300, 1) ||
    !locator.test(value.locator) ||
    typeof value.sourceDigest !== "string" ||
    !digest.test(value.sourceDigest) ||
    !text(value.title, 500) ||
    !text(value.excerpt, 8000) ||
    !text(value.sourceLabel, 500) ||
    (value.verification !== null && !verification(value.verification))
  )
    return false;
  if (
    value.clip !== null &&
    (!isClip(value.clip) || value.kind !== "video_clip" || value.locator !== value.clip.locator)
  )
    return false;
  return !(value.kind === "video_clip" && value.verification !== null && value.clip === null);
}
