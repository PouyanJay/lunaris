import { describe, expect, it } from "vitest";

import type { ActivityFeedItem } from "./activity";
import { deriveTodayXp, XP_DAILY_GOAL } from "./trailXp";

function feedItem(overrides: Partial<ActivityFeedItem>): ActivityFeedItem {
  return {
    eventType: "completed",
    courseId: "c1",
    occurredAt: "2026-07-20T10:00:00Z",
    ...overrides,
  };
}

const NOW = new Date("2026-07-20T18:00:00Z");

describe("deriveTodayXp", () => {
  it("scores today's completed lessons and mastered concepts", () => {
    // Arrange — two completed lessons (10 each) + one mastered concept (5) today.
    const feed = [
      feedItem({ eventType: "completed" }),
      feedItem({ eventType: "completed" }),
      feedItem({ eventType: "mastered" }),
    ];

    // Act / Assert
    expect(deriveTodayXp(feed, NOW).earned).toBe(25);
  });

  it("ignores events from other days", () => {
    // Arrange — yesterday's completion doesn't count toward today.
    const feed = [
      feedItem({ occurredAt: "2026-07-19T23:00:00Z" }),
      feedItem({ occurredAt: "2026-07-20T09:00:00Z" }),
    ];

    // Act / Assert
    expect(deriveTodayXp(feed, NOW).earned).toBe(10);
  });

  it("scores started and verified events as zero", () => {
    // Arrange
    const feed = [feedItem({ eventType: "started" }), feedItem({ eventType: "verified" })];

    // Act / Assert
    expect(deriveTodayXp(feed, NOW).earned).toBe(0);
  });

  it("carries the daily goal", () => {
    // Arrange / Act / Assert
    expect(deriveTodayXp([], NOW).goal).toBe(XP_DAILY_GOAL);
  });
});
