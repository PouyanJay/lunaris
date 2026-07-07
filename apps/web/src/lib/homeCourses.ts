import type { CourseSummary } from "../types/course";

/** Recent-grid cap, and how many other in-progress courses the continue-hero lists beside it. */
export const RECENT_LIMIT = 3;
export const CONTINUE_ROW_LIMIT = 3;

export interface HomeCourses {
  /** In-progress courses (the continue section) — last-opened first, hero then rows. */
  inProgress: CourseSummary[];
  /** Everything else, capped to the recent grid. */
  recent: CourseSummary[];
  /** Whether the library holds more courses than Home surfaces (drives the View-all hatch). */
  hasMore: boolean;
}

/** Split the library into Home's two lanes: the continue section (in-progress) and the recent grid
 *  (everything else, capped). `hasMore` is true when the library holds more than Home shows across
 *  both lanes — the continue section shows the hero plus up to CONTINUE_ROW_LIMIT rows. */
export function splitHomeCourses(courses: CourseSummary[]): HomeCourses {
  const inProgress = courses.filter((course) => course.learnerStatus === "in_progress");
  const recent = courses
    .filter((course) => course.learnerStatus !== "in_progress")
    .slice(0, RECENT_LIMIT);
  const continueShown = Math.min(inProgress.length, 1 + CONTINUE_ROW_LIMIT);
  return { inProgress, recent, hasMore: courses.length > continueShown + recent.length };
}
