/** Format a media runtime in seconds as M:SS (108 → "1:48") — the video caption-row convention.
 *  Distinct from `formatDuration`, which words build-phase spans ("2m 5s"). */
export function formatMediaDuration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
