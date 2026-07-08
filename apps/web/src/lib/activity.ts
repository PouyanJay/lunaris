import { authedFetch } from "./apiClient";

export type LearningEventType = "started" | "completed" | "mastered" | "verified";

export interface ActivityStats {
  currentStreak: number;
  longestStreak: number;
  minutesThisWeek: number;
  conceptsThisWeek: number;
}

/** One of the last-14-days heat squares; `active` covers event-only days (marks without
 *  recorded study minutes still count as studied). */
export interface HeatDay {
  date: string;
  minutes: number;
  active: boolean;
}

/** One bar of the current ISO week's (Monday-first) study-minutes chart. */
export interface WeekDay {
  date: string;
  minutes: number;
}

export interface ActivityFeedItem {
  eventType: LearningEventType;
  courseId: string;
  courseTitle?: string | null;
  lessonId?: string | null;
  lessonTitle?: string | null;
  kcId?: string | null;
  kcLabel?: string | null;
  occurredAt: string;
}

export interface ActivityView {
  stats: ActivityStats;
  heat: HeatDay[];
  week: WeekDay[];
  feed: ActivityFeedItem[];
}

export class ActivityError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ActivityError";
  }
}

/** The viewer's IANA timezone — day/streak math is user-local, so the API needs it. */
function viewerTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** The reader's study-minutes heartbeat — fire-and-forget telemetry. No payload (the server
 *  stamps the minute bucket) and no rejection: losing a beat is acceptable, breaking the
 *  reader is not. */
export async function putHeartbeat(apiBaseUrl: string): Promise<void> {
  try {
    await authedFetch(`${apiBaseUrl}/api/activity/heartbeat`, { method: "PUT" });
  } catch {
    // Best-effort by contract; the next beat retries naturally.
  }
}

/** Fetch the caller's activity snapshot (streaks, study minutes, feed). Rejects with
 *  ActivityError on a transport/HTTP failure so the caller can surface a recoverable message. */
export async function fetchActivity(apiBaseUrl: string, signal?: AbortSignal): Promise<ActivityView> {
  const url = `${apiBaseUrl}/api/activity?tz=${encodeURIComponent(viewerTimeZone())}`;
  let response: Response;
  try {
    response = await authedFetch(url, signal ? { signal } : undefined);
  } catch (cause) {
    throw new ActivityError("Could not reach your activity history.", { cause });
  }
  if (!response.ok) {
    throw new ActivityError(`Couldn't load your activity (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as ActivityView | null;
  // Trust-boundary check: consumers read stats/heat/week/feed unguarded, so an alien payload
  // must become a recoverable error here, never a downstream crash.
  if (
    typeof body?.stats?.currentStreak !== "number" ||
    !Array.isArray(body.heat) ||
    !Array.isArray(body.week) ||
    !Array.isArray(body.feed)
  ) {
    throw new ActivityError("Couldn't read your activity (unexpected response).");
  }
  return body;
}
