import type { HeatDay } from "./activity";

/** Format a Date as its local (not UTC) YYYY-MM-DD calendar day — the same key the activity API
 *  buckets minutes under, computed in the viewer's timezone. Built from local parts on purpose:
 *  `toISOString()` would shift to UTC and mis-pick the day near midnight. */
function localDayKey(now: Date): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Minutes the learner has studied today, read straight from the activity feed's day buckets — a
 *  real, measured number, never an invented score. Zero when today has no recorded minutes yet or
 *  its bucket is absent (best-effort display, not an audit). */
export function deriveTodayMinutes(days: readonly HeatDay[], now: Date): number {
  const key = localDayKey(now);
  return days.find((entry) => entry.date === key)?.minutes ?? 0;
}
