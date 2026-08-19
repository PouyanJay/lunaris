import { describe, expect, it } from "vitest";

import { nextReviewOf, reviewDayLong, reviewDayShort } from "./reviewSchedule";

/** The schedule as the close tells it (P2c T7): the earliest review day and what is due on it,
 *  read off the goodbye turn's meter. Days are named in UTC on every surface, as the server names
 *  them (`review_day`), so the recap's sentence and the ending's sentence agree. */
describe("nextReviewOf", () => {
  const entries = [
    {
      nodeId: "prior",
      concept: "Prior",
      recall: 0.7,
      evidenceCount: 2,
      dueAt: "2026-08-22T12:00:00Z",
    },
    {
      nodeId: "update",
      concept: "Update",
      recall: 0.4,
      evidenceCount: 1,
      dueAt: "2026-08-20T12:00:00Z",
    },
    {
      nodeId: "odds",
      concept: "Odds",
      recall: 0.4,
      evidenceCount: 1,
      dueAt: "2026-08-20T18:30:00Z",
    },
    { nodeId: "later", concept: "Later", recall: 0.1, evidenceCount: 0, dueAt: null },
  ];

  it("names the earliest day and everything due on it, in the meter's order", () => {
    expect(nextReviewOf(entries)).toEqual({
      day: "Thursday 20 August",
      concepts: ["Update", "Odds"],
    });
  });

  it("is nothing when no concept has a day", () => {
    expect(nextReviewOf([{ nodeId: "a", concept: "A", recall: 0.5, evidenceCount: 1 }])).toBeNull();
    expect(nextReviewOf([])).toBeNull();
  });

  it("reads the day in UTC, so a learner near midnight sees the day the server named", () => {
    // Both edges of the UTC day: a local clock east of UTC is already on the 21st at 23:30Z, one
    // west of it is still on the 19th at 00:30Z, so a formatter reading local time fails on one
    // of them wherever the suite runs (except on a UTC machine, where the two agree by luck).
    expect(reviewDayLong("2026-08-20T23:30:00Z")).toBe("Thursday 20 August");
    expect(reviewDayLong("2026-08-20T00:30:00Z")).toBe("Thursday 20 August");
    expect(reviewDayShort("2026-08-20T23:30:00Z")).toBe("Thu 20 Aug");
    expect(reviewDayShort("2026-08-20T00:30:00Z")).toBe("Thu 20 Aug");
  });
});
