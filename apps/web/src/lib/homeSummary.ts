import type { CourseSummary } from "../types/course";

/**
 * The Home greeting subline — honest, cheap figures only: the live streak from the activity API
 * (0 = not loaded or genuinely cold, either way omitted) leading the library-derived counts.
 * A global "concepts mastered" aggregate would undercount (events carry no backfill), so it stays
 * out. An empty library gets a neutral workspace line regardless — a fresh account can't have a
 * real streak, and the first-run hero below carries the call to action.
 */
export function homeSubline(courses: CourseSummary[], streak: number = 0): string {
  if (courses.length === 0) return "Your learning workspace";

  const lessonsDone = courses.reduce((total, course) => total + course.lessonsDone, 0);
  const inProgress = courses.filter((course) => course.learnerStatus === "in_progress").length;

  const parts: string[] = [];
  if (streak >= 1) parts.push(`${streak}-day streak`);
  if (lessonsDone > 0) {
    parts.push(`${lessonsDone} ${lessonsDone === 1 ? "lesson" : "lessons"} completed`);
  }
  if (inProgress > 0) parts.push(`${inProgress} in progress`);
  if (parts.length > 0) return parts.join(" · ");

  return `${courses.length} ${courses.length === 1 ? "course" : "courses"} in your library`;
}
