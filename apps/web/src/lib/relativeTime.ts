/** Compact, locale-aware "time ago" for run timestamps — the sidebar's mono time column. */

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto", style: "narrow" });

/**
 * Format an ISO timestamp as a short relative string ("just now", "5 min ago", "2 days ago").
 * `now` is injectable for deterministic tests; it defaults to the wall clock.
 */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";

  const seconds = Math.round((then - now) / 1000); // negative = in the past
  const absSeconds = Math.abs(seconds);

  if (absSeconds < MINUTE) return "just now";
  if (absSeconds < HOUR) return formatter.format(Math.round(seconds / MINUTE), "minute");
  if (absSeconds < DAY) return formatter.format(Math.round(seconds / HOUR), "hour");
  return formatter.format(Math.round(seconds / DAY), "day");
}
