import { describe, expect, it } from "vitest";

import type { ActivityFeedItem } from "./activity";
import { feedLine, groupFeedByDay } from "./activityFeed";

// Local-calendar fixtures, never absolute-UTC literals: grouping derives the LOCAL day, so a
// fixed "...T12:00:00Z" flips groups when the suite runs in Tokyo or Auckland.
const NOW = new Date(2026, 6, 8, 15, 0, 0);
const atDaysAgo = (days: number, hour = 12) =>
  new Date(2026, 6, 8 - days, hour).toISOString();

function item(overrides: Partial<ActivityFeedItem> = {}): ActivityFeedItem {
  return {
    eventType: "completed",
    courseId: "course-1",
    courseTitle: "How HTTPS works",
    lessonId: "m-1-l0",
    lessonTitle: "Lesson 1 · Fundamentals",
    kcId: null,
    kcLabel: null,
    occurredAt: atDaysAgo(0),
    ...overrides,
  };
}

describe("groupFeedByDay", () => {
  it("labels groups Today / Yesterday / a formatted date, preserving order", () => {
    // Arrange — newest-first, spanning three local days.
    const feed = [
      item({ occurredAt: atDaysAgo(0) }),
      item({ occurredAt: atDaysAgo(1, 18), lessonId: "a" }),
      item({ occurredAt: atDaysAgo(5, 9), lessonId: "b" }),
    ];

    // Act
    const groups = groupFeedByDay(feed, NOW);

    // Assert — the dated label follows the RUNTIME locale (product behavior), so the expectation
    // is formatted the same way rather than hardcoding an English month name.
    const datedLabel = new Intl.DateTimeFormat(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
    }).format(new Date(2026, 6, 3, 12));
    expect(groups.map((group) => group.label)).toEqual(["Today", "Yesterday", datedLabel]);
    expect(groups.map((group) => group.items.length)).toEqual([1, 1, 1]);
  });

  it("keeps multiple same-day items in one group", () => {
    // Arrange
    const feed = [
      item({ occurredAt: atDaysAgo(0, 12) }),
      item({ occurredAt: atDaysAgo(0, 9), lessonId: "a" }),
    ];

    // Act
    const groups = groupFeedByDay(feed, NOW);

    // Assert
    expect(groups).toHaveLength(1);
    expect(groups[0]?.items).toHaveLength(2);
  });

  it("returns nothing for an empty feed", () => {
    expect(groupFeedByDay([], NOW)).toEqual([]);
  });
});

describe("feedLine", () => {
  it("words each event type with its real titles", () => {
    expect(feedLine(item())).toBe("Completed Lesson 1 · Fundamentals in How HTTPS works");
    expect(feedLine(item({ eventType: "started" }))).toBe(
      "Started Lesson 1 · Fundamentals in How HTTPS works",
    );
    expect(
      feedLine(
        item({
          eventType: "mastered",
          lessonId: null,
          lessonTitle: null,
          kcId: "kc-a",
          kcLabel: "TLS fundamentals",
        }),
      ),
    ).toBe("Mastered TLS fundamentals in How HTTPS works");
  });

  it("falls back honestly when titles were not recorded", () => {
    // A course that could not be loaded at write time carries no titles — never invent them.
    expect(feedLine(item({ lessonTitle: null, courseTitle: null }))).toBe("Completed a lesson");
    expect(
      feedLine(item({ eventType: "mastered", lessonTitle: null, kcLabel: null, kcId: "kc-a" })),
    ).toBe("Mastered a concept in How HTTPS works");
  });
});
