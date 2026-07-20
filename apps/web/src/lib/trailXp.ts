import type { ActivityFeedItem, LearningEventType } from "./activity";

/** Points a learning event is worth in the Trail's motivation display.
 *
 *  XP is a presentation LENS over the real, append-only `learning_events` feed — never stored and
 *  never fabricated (the events themselves are what the pipeline records). Finishing a lesson is
 *  the headline achievement; mastering a concept is the smaller, more frequent one. `started` is
 *  not an achievement, and `verified` is reserved (nothing emits it today). */
const XP_PER_EVENT: Record<LearningEventType, number> = {
  completed: 10,
  mastered: 5,
  started: 0,
  verified: 0,
};

/** The day's XP target — a client-side product default (there is no persisted goal). */
export const XP_DAILY_GOAL = 30;

export interface TrailXp {
  /** XP earned from today's events (learner-local day). */
  earned: number;
  /** The day's target. */
  goal: number;
}

/** Whether two instants fall on the same local calendar day. */
function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Today's XP: the deterministic score over the real activity feed, counting only events that
 *  occurred on the current local day. The feed is capped upstream (newest 50 within 30 days), so
 *  an extraordinarily active day can under-count — this is a motivation display, not an audit. */
export function deriveTodayXp(feed: ActivityFeedItem[], now: Date): TrailXp {
  const earned = feed.reduce((sum, item) => {
    const occurred = new Date(item.occurredAt);
    if (Number.isNaN(occurred.getTime()) || !sameLocalDay(occurred, now)) return sum;
    return sum + XP_PER_EVENT[item.eventType];
  }, 0);
  return { earned, goal: XP_DAILY_GOAL };
}
