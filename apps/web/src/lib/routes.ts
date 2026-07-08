import { matchPath } from "react-router";

import type { CourseView } from "../components/reader/ViewToggle";

/** The app's fixed destinations — one source of truth for path literals (sidebar + router). */
export const ROUTES = {
  home: "/",
  composer: "/new",
  library: "/courses",
  activity: "/activity",
  bookmarks: "/bookmarks",
  settings: "/settings",
  admin: "/admin",
} as const;

const COURSE_VIEWS: CourseView[] = ["overview", "lessons", "map", "build", "corpus"];

/** The reader segment was spelled "learn" before Overview became the landing tab — old
 *  bookmarks and shared links keep resolving. */
const LEGACY_READER_SEGMENT = "learn";

/** The shell's navigation surfaces, resolved from the URL. A course canvas is keyed by courseId
 *  with an optional view segment (default Overview — the course's landing tab); anything
 *  unrecognized — including a bogus view segment — renders the designed not-found canvas,
 *  never a blank. */
export type ShellRoute =
  | { kind: "home" }
  | { kind: "composer" }
  | { kind: "settings" }
  | { kind: "admin" }
  | { kind: "library" }
  | { kind: "activity" }
  | { kind: "bookmarks" }
  | { kind: "course"; courseId: string; view: CourseView; lessonId?: string }
  | { kind: "not-found" };

export function resolveRoute(pathname: string): ShellRoute {
  if (pathname === ROUTES.home) return { kind: "home" };
  // The composer is its own place at /new; Home is the dashboard at /.
  if (pathname === ROUTES.composer) return { kind: "composer" };
  if (pathname === ROUTES.settings) return { kind: "settings" };
  if (pathname === ROUTES.admin) return { kind: "admin" };
  if (pathname === ROUTES.library) return { kind: "library" };
  if (pathname === ROUTES.activity) return { kind: "activity" };
  if (pathname === ROUTES.bookmarks) return { kind: "bookmarks" };
  const course = matchPath("/courses/:courseId/:view?/:lessonId?", pathname);
  if (course?.params.courseId) {
    const rawView = course.params.view ?? "overview";
    const view = rawView === LEGACY_READER_SEGMENT ? "lessons" : rawView;
    const lessonId = course.params.lessonId;
    if ((COURSE_VIEWS as string[]).includes(view)) {
      // Only the reader addresses a lesson (P6); a trailing segment under any other view is
      // an unknown URL, not a silently-dropped extra.
      if (lessonId !== undefined && view !== "lessons") return { kind: "not-found" };
      return {
        kind: "course",
        courseId: course.params.courseId,
        view: view as CourseView,
        ...(lessonId !== undefined ? { lessonId } : {}),
      };
    }
  }
  return { kind: "not-found" };
}

/** The canonical URL for a course view — Overview is the bare course path, not a segment. */
export function coursePath(courseId: string, view: CourseView = "overview"): string {
  return view === "overview" ? `/courses/${courseId}` : `/courses/${courseId}/${view}`;
}

/** The canonical URL for a reading position: a lesson inside the reader (P6 lesson-in-URL). */
export function lessonPath(courseId: string, lessonId: string): string {
  return `/courses/${courseId}/lessons/${lessonId}`;
}
