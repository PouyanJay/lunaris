import type { ActivityFeedItem } from "./activity";

export interface FeedGroup {
  label: string;
  items: ActivityFeedItem[];
}

const dateLabel = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  month: "long",
  day: "numeric",
});

function startOfLocalDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function labelFor(occurred: Date, now: Date): string {
  const dayMs = 24 * 60 * 60 * 1000;
  const daysBack = Math.round((startOfLocalDay(now) - startOfLocalDay(occurred)) / dayMs);
  if (daysBack <= 0) return "Today";
  if (daysBack === 1) return "Yesterday";
  return dateLabel.format(occurred);
}

/** Fold the (newest-first) feed into per-local-day groups — Today / Yesterday / a formatted
 *  date. Day boundaries are the viewer's local calendar, matching the API's tz-local stats. */
export function groupFeedByDay(feed: ActivityFeedItem[], now: Date = new Date()): FeedGroup[] {
  const groups: FeedGroup[] = [];
  for (const item of feed) {
    const label = labelFor(new Date(item.occurredAt), now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

const VERBS = {
  started: "Started",
  completed: "Completed",
  mastered: "Mastered",
  verified: "Verified",
} as const;

/** One feed row's sentence, from the event's denormalized titles. Missing titles (the course
 *  wasn't loadable when the event was recorded) fall back to honest generics — never guessed. */
export function feedLine(item: ActivityFeedItem): string {
  const verb = VERBS[item.eventType];
  const subject =
    item.eventType === "mastered"
      ? (item.kcLabel ?? "a concept")
      : (item.lessonTitle ?? "a lesson");
  return item.courseTitle ? `${verb} ${subject} in ${item.courseTitle}` : `${verb} ${subject}`;
}
