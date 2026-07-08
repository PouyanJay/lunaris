import type { CourseProgress } from "./progress";

/** A lesson's display state in course lists (Overview rows, reader outline): the learner's
 *  progress mark, with `up_next` for an unmarked lesson or an absent snapshot (offline). */
export type LessonState = "done" | "in_progress" | "up_next";

export function lessonStateFor(progress: CourseProgress | null, lessonId: string): LessonState {
  const mark = progress?.lessons.find((lesson) => lesson.lessonId === lessonId);
  if (mark?.state === "done") return "done";
  if (mark?.state === "in_progress") return "in_progress";
  return "up_next";
}
