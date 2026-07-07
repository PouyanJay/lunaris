import { matchPath } from "react-router";

import type { CourseView } from "../components/reader/ViewToggle";

/** The app's fixed destinations — one source of truth for path literals (sidebar + router). */
export const ROUTES = {
  home: "/",
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
  | { kind: "settings" }
  | { kind: "admin" }
  | { kind: "library" }
  | { kind: "activity" }
  | { kind: "bookmarks" }
  | { kind: "course"; courseId: string; view: CourseView }
  | { kind: "not-found" };

export function resolveRoute(pathname: string): ShellRoute {
  if (pathname === ROUTES.home) return { kind: "home" };
  // /new is an alias for the composer; an effect normalizes the URL to "/".
  if (pathname === "/new") return { kind: "home" };
  if (pathname === ROUTES.settings) return { kind: "settings" };
  if (pathname === ROUTES.admin) return { kind: "admin" };
  if (pathname === ROUTES.library) return { kind: "library" };
  if (pathname === ROUTES.activity) return { kind: "activity" };
  if (pathname === ROUTES.bookmarks) return { kind: "bookmarks" };
  const course = matchPath("/courses/:courseId/:view?", pathname);
  if (course?.params.courseId) {
    const rawView = course.params.view ?? "overview";
    const view = rawView === LEGACY_READER_SEGMENT ? "lessons" : rawView;
    if ((COURSE_VIEWS as string[]).includes(view)) {
      return { kind: "course", courseId: course.params.courseId, view: view as CourseView };
    }
  }
  return { kind: "not-found" };
}

/** The canonical URL for a course view — Overview is the bare course path, not a segment. */
export function coursePath(courseId: string, view: CourseView = "overview"): string {
  return view === "overview" ? `/courses/${courseId}` : `/courses/${courseId}/${view}`;
}
