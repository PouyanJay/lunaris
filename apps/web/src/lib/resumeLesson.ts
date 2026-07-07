import { flattenLessons } from "./flattenLessons";
import type { CourseProgress } from "./progress";
import type { Course } from "../types/course";

/** Where a learner should pick a course back up — the resume lesson and its position, for Home's
 *  continue-learning hero ("Lesson N of M" + the next-up line). */
export interface ResumePoint {
  lessonId: string;
  /** 1-based position of the resume lesson in course reading order. */
  number: number;
  /** Total authored lessons in the course. */
  total: number;
  /** The resume lesson's owning module title — what the reader and Overview show as its heading. */
  moduleTitle: string;
}

/** Resolve the resume point: the learner's recorded position when it still maps to a lesson, else
 *  the first unfinished lesson, else the first lesson. Null only when the course has no lessons. */
export function resolveResumePoint(
  course: Course,
  progress: CourseProgress | null,
): ResumePoint | null {
  const flat = flattenLessons(course);
  const first = flat[0];
  if (!first) return null;

  const done = new Set(
    (progress?.lessons ?? []).filter((mark) => mark.state === "done").map((mark) => mark.lessonId),
  );
  const recorded =
    progress?.lastLessonId && flat.some((entry) => entry.lesson.id === progress.lastLessonId)
      ? progress.lastLessonId
      : undefined;
  const firstUnfinished = flat.find((entry) => !done.has(entry.lesson.id))?.lesson.id;
  const lessonId = recorded ?? firstUnfinished ?? first.lesson.id;

  const entry = flat.find((item) => item.lesson.id === lessonId) ?? first;
  return {
    lessonId: entry.lesson.id,
    number: entry.index + 1,
    total: flat.length,
    moduleTitle: entry.module.title,
  };
}
