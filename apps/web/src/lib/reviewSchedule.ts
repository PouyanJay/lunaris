import type { MeterEntrySpec } from "./surfaceSpec";

/** The next review, as the ending says it (P2c T7): the earliest day any concept on the meter is
 *  due back, and every concept due that day, in the meter's order (the map's). */
export interface NextReview {
  /** "Thursday 20 August": the day, never the time. */
  day: string;
  concepts: string[];
}

/** Days are named in UTC on every surface, as the server names them (`review_day`): the schedule
 *  is an instant on the map's calendar and the server knows no learner timezone, so the recap's
 *  sentence, the meter row and the ending agree — a learner far from UTC may see a day that is not
 *  their own near midnight, which is chosen over three surfaces disagreeing (AD21). */
const LONG = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});
const SHORT = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

/** "Thursday 20 August", for a sentence. */
export function reviewDayLong(iso: string): string {
  return LONG.format(new Date(iso));
}

/** "Thu 20 Aug", for a meter row. */
export function reviewDayShort(iso: string): string {
  return SHORT.format(new Date(iso));
}

/** The earliest review day on the meter and what is due on it, or `null` when nothing is
 *  scheduled (a session that graded nothing, or one stored before the schedule existed). */
export function nextReviewOf(entries: readonly MeterEntrySpec[]): NextReview | null {
  const dated = entries.filter((entry): entry is MeterEntrySpec & { dueAt: string } =>
    Boolean(entry.dueAt),
  );
  if (dated.length === 0) return null;
  const first = dated.reduce((earliest, entry) =>
    Date.parse(entry.dueAt) < Date.parse(earliest.dueAt) ? entry : earliest,
  );
  const day = reviewDayLong(first.dueAt);
  return {
    day,
    concepts: dated.filter((entry) => reviewDayLong(entry.dueAt) === day).map((e) => e.concept),
  };
}
