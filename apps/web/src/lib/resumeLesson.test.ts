import { describe, expect, it } from "vitest";

import { resolveResumePoint } from "./resumeLesson";
import { makeCourse, makeLesson, makeModule } from "../test/fixtures";
import type { CourseProgress } from "./progress";
import type { Course } from "../types/course";

/** A three-lesson course across two modules, for resume-position tests. */
function threeLessonCourse(): Course {
  return makeCourse({
    modules: [
      makeModule({
        id: "m-a",
        title: "Foundations",
        lessons: [makeLesson({ id: "l-1" }), makeLesson({ id: "l-2" })],
      }),
      makeModule({
        id: "m-b",
        title: "Applications",
        lessons: [makeLesson({ id: "l-3" })],
      }),
    ],
  });
}

function progress(overrides: Partial<CourseProgress> = {}): CourseProgress {
  return { courseId: "course-test", objectives: [], lessons: [], ...overrides };
}

describe("resolveResumePoint", () => {
  it("resumes at the recorded last-opened lesson when it still exists", () => {
    const point = resolveResumePoint(
      threeLessonCourse(),
      progress({ lastLessonId: "l-2" }),
    );
    expect(point).toEqual({ lessonId: "l-2", number: 2, total: 3, moduleTitle: "Foundations" });
  });

  it("falls back to the first unfinished lesson when there is no recorded position", () => {
    const point = resolveResumePoint(
      threeLessonCourse(),
      progress({ lessons: [{ lessonId: "l-1", state: "done", updatedAt: "2026-07-01T00:00:00Z" }] }),
    );
    expect(point?.lessonId).toBe("l-2");
    expect(point?.number).toBe(2);
  });

  it("crosses a module boundary for the resume module title", () => {
    const point = resolveResumePoint(
      threeLessonCourse(),
      progress({
        lessons: [
          { lessonId: "l-1", state: "done", updatedAt: "2026-07-01T00:00:00Z" },
          { lessonId: "l-2", state: "done", updatedAt: "2026-07-01T00:00:00Z" },
        ],
      }),
    );
    expect(point).toEqual({ lessonId: "l-3", number: 3, total: 3, moduleTitle: "Applications" });
  });

  it("defaults to the first lesson with no progress at all", () => {
    const point = resolveResumePoint(threeLessonCourse(), null);
    expect(point?.lessonId).toBe("l-1");
    expect(point?.number).toBe(1);
  });

  it("returns null for a course with no authored lessons", () => {
    const empty = makeCourse({ modules: [makeModule({ lessons: [] })] });
    expect(resolveResumePoint(empty, null)).toBeNull();
  });
});
