import { describe, expect, it } from "vitest";

import { splitHomeCourses } from "./homeCourses";
import { makeCourseSummary } from "../test/fixtures";
import type { LearnerCourseStatus } from "../types/course";

function summary(id: string, status: LearnerCourseStatus) {
  return makeCourseSummary({ id, learnerStatus: status });
}

describe("splitHomeCourses", () => {
  it("routes in-progress courses to the continue lane and the rest to the recent grid", () => {
    const { inProgress, recent } = splitHomeCourses([
      summary("a", "in_progress"),
      summary("b", "completed"),
      summary("c", "not_started"),
    ]);
    expect(inProgress.map((course) => course.id)).toEqual(["a"]);
    expect(recent.map((course) => course.id)).toEqual(["b", "c"]);
  });

  it("caps the recent grid at three", () => {
    const courses = Array.from({ length: 5 }, (_, i) => summary(`c-${i}`, "completed"));
    expect(splitHomeCourses(courses).recent).toHaveLength(3);
  });

  it("flags hasMore only when the library holds more than Home surfaces", () => {
    const four = Array.from({ length: 4 }, (_, i) => summary(`c-${i}`, "completed"));
    // 4 completed → recent shows 3 → one is hidden.
    expect(splitHomeCourses(four).hasMore).toBe(true);

    const three = Array.from({ length: 3 }, (_, i) => summary(`c-${i}`, "completed"));
    expect(splitHomeCourses(three).hasMore).toBe(false);
  });

  it("counts the whole continue lane (hero + up to 3 rows) as shown", () => {
    // 4 in-progress = hero + 3 rows, all shown; nothing hidden.
    const four = Array.from({ length: 4 }, (_, i) => summary(`c-${i}`, "in_progress"));
    expect(splitHomeCourses(four).hasMore).toBe(false);
    // A 5th in-progress course overflows the continue lane.
    const five = [...four, summary("c-5", "in_progress")];
    expect(splitHomeCourses(five).hasMore).toBe(true);
  });
});
