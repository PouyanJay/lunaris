import type { CourseSummary } from "../types/course";

/**
 * The Home greeting subline — an honest, cheap figure derived from the library summaries. A global
 * "concepts mastered" aggregate isn't exposed by the courses API yet, and streak lands in Phase 8;
 * until then this counts completed lessons and in-progress courses. An empty library gets a neutral
 * workspace line (the first-run hero below carries the real call to action).
 */
export function homeSubline(courses: CourseSummary[]): string {
  if (courses.length === 0) return "Your learning workspace";

  const lessonsDone = courses.reduce((total, course) => total + course.lessonsDone, 0);
  const inProgress = courses.filter((course) => course.learnerStatus === "in_progress").length;

  const parts: string[] = [];
  if (lessonsDone > 0) {
    parts.push(`${lessonsDone} ${lessonsDone === 1 ? "lesson" : "lessons"} completed`);
  }
  if (inProgress > 0) parts.push(`${inProgress} in progress`);
  if (parts.length > 0) return parts.join(" · ");

  return `${courses.length} ${courses.length === 1 ? "course" : "courses"} in your library`;
}
