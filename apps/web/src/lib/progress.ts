import { authedFetch } from "./apiClient";

/** A lesson's learner state — in_progress on first open, done on completion. */
export type LessonState = "in_progress" | "done";

/** One understood objective, keyed by its module + position (objectives carry no id). */
export interface ObjectiveProgress {
  moduleId: string;
  objectiveIndex: number;
  understoodAt: string;
}

export interface LessonProgress {
  lessonId: string;
  state: LessonState;
  updatedAt: string;
}

/** Derived course-level rollup — recomputed by the API per read, never stored. */
export interface ProgressSummary {
  understoodCount: number;
  objectiveTotal: number;
  lessonsDone: number;
  lessonTotal: number;
  percent: number;
}

/** The caller's progress on one course — raw marks plus rollups derived against the course
 *  payload (summary null / kcMastery empty when the course isn't loadable). */
export interface CourseProgress {
  courseId: string;
  objectives: ObjectiveProgress[];
  lessons: LessonProgress[];
  summary?: ProgressSummary | null;
  kcMastery?: Record<string, boolean>;
}

export async function fetchCourseProgress(
  apiBaseUrl: string,
  courseId: string,
  signal?: AbortSignal,
): Promise<CourseProgress> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/progress`,
    { signal: signal ?? null },
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as CourseProgress;
}

export async function putObjectiveProgress(
  apiBaseUrl: string,
  courseId: string,
  mark: { moduleId: string; objectiveIndex: number; understood: boolean },
): Promise<void> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/progress/objective`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mark) },
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

export async function putLessonProgress(
  apiBaseUrl: string,
  courseId: string,
  mark: { lessonId: string; state: LessonState },
): Promise<void> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/progress/lesson`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mark) },
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}
