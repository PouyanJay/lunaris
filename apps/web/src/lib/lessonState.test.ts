import { describe, expect, it } from "vitest";

import { lessonStateFor } from "./lessonState";
import type { CourseProgress } from "./progress";

const progress: CourseProgress = {
  courseId: "c1",
  objectives: [],
  lessons: [
    { lessonId: "l-done", state: "done", updatedAt: "2026-07-07T00:00:00Z" },
    { lessonId: "l-open", state: "in_progress", updatedAt: "2026-07-07T00:00:00Z" },
  ],
};

describe("lessonStateFor", () => {
  it("maps the learner's marks onto display states", () => {
    expect(lessonStateFor(progress, "l-done")).toBe("done");
    expect(lessonStateFor(progress, "l-open")).toBe("in_progress");
    expect(lessonStateFor(progress, "l-unmarked")).toBe("up_next");
  });

  it("treats an absent snapshot (offline) as up_next", () => {
    expect(lessonStateFor(null, "l-done")).toBe("up_next");
  });
});
