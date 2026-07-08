import { describe, expect, it } from "vitest";

import { homeSubline } from "./homeSummary";
import { makeCourseSummary } from "../test/fixtures";

describe("homeSubline", () => {
  it("counts completed lessons and in-progress courses", () => {
    const line = homeSubline([
      makeCourseSummary({ id: "a", lessonsDone: 4, learnerStatus: "in_progress" }),
      makeCourseSummary({ id: "b", lessonsDone: 6, learnerStatus: "completed" }),
      makeCourseSummary({ id: "c", lessonsDone: 0, learnerStatus: "not_started" }),
    ]);
    expect(line).toBe("10 lessons completed · 1 in progress");
  });

  it("singularises a lone completed lesson", () => {
    expect(
      homeSubline([makeCourseSummary({ lessonsDone: 1, learnerStatus: "completed" })]),
    ).toBe("1 lesson completed");
  });

  it("shows only the in-progress count when no lessons are done yet", () => {
    expect(
      homeSubline([
        makeCourseSummary({ id: "a", lessonsDone: 0, learnerStatus: "in_progress" }),
        makeCourseSummary({ id: "b", lessonsDone: 0, learnerStatus: "not_started" }),
      ]),
    ).toBe("1 in progress");
  });

  it("falls back to a library count when nothing has been touched", () => {
    expect(
      homeSubline([
        makeCourseSummary({ id: "a", lessonsDone: 0, learnerStatus: "not_started" }),
        makeCourseSummary({ id: "b", lessonsDone: 0, learnerStatus: "not_started" }),
      ]),
    ).toBe("2 courses in your library");
  });

  it("gives an empty library a neutral workspace line", () => {
    expect(homeSubline([])).toBe("Your learning workspace");
  });

  it("leads with the streak when one is alight", () => {
    expect(
      homeSubline(
        [makeCourseSummary({ lessonsDone: 6, learnerStatus: "completed" })],
        5,
      ),
    ).toBe("5-day streak · 6 lessons completed");
  });

  it("singularises a one-day streak and omits a cold one", () => {
    const courses = [makeCourseSummary({ lessonsDone: 1, learnerStatus: "completed" })];
    expect(homeSubline(courses, 1)).toBe("1-day streak · 1 lesson completed");
    expect(homeSubline(courses, 0)).toBe("1 lesson completed");
  });

  it("never decorates the empty-library line with a streak", () => {
    // A fresh account can't have a real streak; the first-run hero owns the call to action.
    expect(homeSubline([], 3)).toBe("Your learning workspace");
  });
});
