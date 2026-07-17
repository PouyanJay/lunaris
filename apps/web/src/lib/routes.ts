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
  account: "/account",
  /** Legacy — kept so old links/bookmarks still resolve; redirects to {@link ROUTES.account}. */
  profile: "/profile",
  admin: "/admin",
} as const;

/** The Settings surface's sub-sections, in nav order. One source of truth for the sub-nav, the
 *  URL segment (`/settings/:section`), and the section renderer. */
export const SETTINGS_SECTIONS = [
  "system",
  "appearance",
  "llm",
  "video",
  "voice",
  "tools",
  "sources",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

/** The default section for the bare `/settings` path. */
export const DEFAULT_SETTINGS_SECTION: SettingsSection = "system";

function isSettingsSection(value: string): value is SettingsSection {
  return (SETTINGS_SECTIONS as readonly string[]).includes(value);
}

/** The canonical URL for a settings section (Settings sub-nav + deep links). */
export function settingsPath(section: SettingsSection): string {
  return `${ROUTES.settings}/${section}`;
}

/** The Account surface's sub-sections. Admins get a sub-nav (User account | Admin Portal); a
 *  non-admin only ever sees `user-account`. One source of truth for the nav, the URL segment
 *  (`/account/:section`), and the section renderer. */
export const ACCOUNT_SECTIONS = ["user-account", "admin-portal"] as const;

export type AccountSection = (typeof ACCOUNT_SECTIONS)[number];

export const DEFAULT_ACCOUNT_SECTION: AccountSection = "user-account";

function isAccountSection(value: string): value is AccountSection {
  return (ACCOUNT_SECTIONS as readonly string[]).includes(value);
}

/** The canonical URL for an account section (Account sub-nav + deep links). */
export function accountPath(section: AccountSection): string {
  return section === DEFAULT_ACCOUNT_SECTION ? ROUTES.account : `${ROUTES.account}/${section}`;
}

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
  | { kind: "settings"; section: SettingsSection }
  | { kind: "account"; section: AccountSection }
  | { kind: "library" }
  | { kind: "activity" }
  | { kind: "bookmarks" }
  | { kind: "course"; courseId: string; view: CourseView; lessonId?: string }
  | { kind: "not-found" };

export function resolveRoute(pathname: string): ShellRoute {
  if (pathname === ROUTES.home) return { kind: "home" };
  // The composer is its own place at /new; Home is the dashboard at /.
  if (pathname === ROUTES.composer) return { kind: "composer" };
  // Bare /settings lands on the default section; /settings/:section deep-links a section (an
  // unknown segment is a not-found URL, not a silent default).
  if (pathname === ROUTES.settings) {
    return { kind: "settings", section: DEFAULT_SETTINGS_SECTION };
  }
  const settings = matchPath(`${ROUTES.settings}/:section`, pathname);
  if (settings?.params.section) {
    return isSettingsSection(settings.params.section)
      ? { kind: "settings", section: settings.params.section }
      : { kind: "not-found" };
  }
  // Bare /account (and the legacy /profile) land on the default section; /account/:section
  // deep-links a section; /admin folds into the Account surface's Admin Portal section.
  if (pathname === ROUTES.account || pathname === ROUTES.profile) {
    return { kind: "account", section: DEFAULT_ACCOUNT_SECTION };
  }
  if (pathname === ROUTES.admin) return { kind: "account", section: "admin-portal" };
  const account = matchPath(`${ROUTES.account}/:section`, pathname);
  if (account?.params.section) {
    return isAccountSection(account.params.section)
      ? { kind: "account", section: account.params.section }
      : { kind: "not-found" };
  }
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
