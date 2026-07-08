import { describe, expect, it } from "vitest";

import type { ActivityFeedItem } from "./activity";
import { feedLine, groupFeedByDay } from "./activityFeed";

const NOW = new Date("2026-07-08T15:00:00Z");

function item(overrides: Partial<ActivityFeedItem> = {}): ActivityFeedItem {
  return {
    eventType: "completed",
    courseId: "course-1",
    courseTitle: "How HTTPS works",
    lessonId: "m-1-l0",
    lessonTitle: "Lesson 1 · Fundamentals",
    kcId: null,
    kcLabel: null,
    occurredAt: "2026-07-08T12:00:00Z",
    ...overrides,
  };
}

describe("groupFeedByDay", () => {
  it("labels groups Today / Yesterday / a formatted date, preserving order", () => {
    // Arrange — newest-first, spanning three local days.
    const feed = [
      item({ occurredAt: "2026-07-08T12:00:00Z" }),
      item({ occurredAt: "2026-07-07T18:00:00Z", lessonId: "a" }),
      item({ occurredAt: "2026-07-03T09:00:00Z", lessonId: "b" }),
    ];

    // Act
    const groups = groupFeedByDay(feed, NOW);

    // Assert
    expect(groups.map((group) => group.label)).toEqual([
      "Today",
      "Yesterday",
      expect.stringMatching(/july 3/i),
    ]);
    expect(groups.map((group) => group.items.length)).toEqual([1, 1, 1]);
  });

  it("keeps multiple same-day items in one group", () => {
    // Arrange
    const feed = [
      item({ occurredAt: "2026-07-08T12:00:00Z" }),
      item({ occurredAt: "2026-07-08T09:00:00Z", lessonId: "a" }),
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
