import { Link } from "react-router";

import { ContinueLearning } from "./ContinueLearning";
import { CourseCard } from "../course/CourseCard";
import { LiveBuildBanner } from "../course/LiveBuildBanner";
import { ConfirmDialog } from "../overlays/ConfirmDialog";
import { Button } from "../primitives/Button";
import { ErrorState } from "../states/ErrorState";
import { useActivity, type ActivityState } from "../../hooks/useActivity";
import { useCourseDeletion } from "../../hooks/useCourseDeletion";
import { useLibrary, type LibraryState } from "../../hooks/useLibrary";
import { displayNameFromEmail, greetingForHour } from "../../lib/greeting";
import { RECENT_LIMIT, splitHomeCourses } from "../../lib/homeCourses";
import { homeSubline } from "../../lib/homeSummary";
import { ROUTES } from "../../lib/routes";
import type { CourseRun, CourseSummary } from "../../types/course";
import styles from "./HomeDashboard.module.css";

interface HomeDashboardProps {
  apiBaseUrl: string;
  /** The signed-in caller's email — the greeting name is derived from it (offline: null). */
  userEmail: string | null;
  /** Run history from the shell's useRuns — RUNNING rows drive the live-build banner. */
  runs: CourseRun[];
  /** Open the composer (first-run recovery + the empty state's action). */
  onNewCourse: () => void;
  /** Resume into a course's reader — at the resume lesson when known (the continue-hero). */
  onResumeLesson: (courseId: string, lessonId?: string) => void;
  /** Open a course's Overview tab. */
  onViewCourse: (courseId: string) => void;
}

const SKELETON_CARDS = RECENT_LIMIT;

/** The greeting subline — honest figures once loaded (the live streak leads when alight);
 *  neutral while in flight, and unchanged when the activity backend is unreachable. */
function subline(state: LibraryState, activity: ActivityState): string {
  if (state.status !== "ready") return "Your learning workspace";
  const streak = activity.status === "ready" ? activity.view.stats.currentStreak : 0;
  return homeSubline(state.courses, streak);
}

/** The live-build banners: one amber strip per genuinely running build, each linking into the
 *  building course's canvas. Nothing renders when no build is in flight. */
function LiveBuilds({ runs }: { runs: CourseRun[] }) {
  const running = runs.filter((run) => run.status === "running");
  if (running.length === 0) return null;
  return (
    <div className={styles.banners}>
      {running.map((run) => (
        <LiveBuildBanner key={run.runId} run={run} cta="Open build →" />
      ))}
    </div>
  );
}

/** The first-run hero: no courses yet → name a topic. A real next step, never a blank canvas. */
function FirstRunHero({ onNewCourse }: { onNewCourse: () => void }) {
  return (
    <section className={styles.firstRun}>
      <p className="eyebrow">Get started</p>
      <h2 className={styles.firstRunTitle}>Build your first course</h2>
      <p className={styles.firstRunBody}>
        Name a topic and the agent researches, plans, and writes a grounded course — it will land
        here, ready to learn.
      </p>
      <Button variant="accent" onClick={onNewCourse}>
        New course
      </Button>
    </section>
  );
}

interface HomeBodyProps {
  apiBaseUrl: string;
  state: LibraryState;
  reload: () => void;
  onNewCourse: () => void;
  onResumeLesson: (courseId: string, lessonId?: string) => void;
  onViewCourse: (courseId: string) => void;
  onRequestDelete: (course: CourseSummary) => void;
}

/** The data region below the greeting: loading skeleton, recoverable error, first-run empty, or —
 *  once courses exist — the continue-learning section (in-progress) over the recent grid
 *  (everything else), with a "View all" escape hatch whenever the library holds more than Home
 *  surfaces. */
function HomeBody({
  apiBaseUrl,
  state,
  reload,
  onNewCourse,
  onResumeLesson,
  onViewCourse,
  onRequestDelete,
}: HomeBodyProps) {
  if (state.status === "loading") {
    return (
      <ul className={styles.grid} aria-busy="true" aria-label="Loading your courses">
        {Array.from({ length: SKELETON_CARDS }, (_, index) => (
          <li key={index} className={styles.skeletonCard} />
        ))}
      </ul>
    );
  }

  if (state.status === "error") {
    return <ErrorState eyebrow="Home" message={state.message} onRetry={reload} />;
  }

  if (state.courses.length === 0) {
    return <FirstRunHero onNewCourse={onNewCourse} />;
  }

  const { inProgress, recent, hasMore } = splitHomeCourses(state.courses);

  return (
    <>
      {inProgress.length > 0 && (
        <ContinueLearning
          apiBaseUrl={apiBaseUrl}
          inProgress={inProgress}
          onResume={onResumeLesson}
          onViewCourse={onViewCourse}
        />
      )}
      {recent.length > 0 && (
        <RecentCourses courses={recent} onRequestDelete={onRequestDelete} />
      )}
      {hasMore && (
        <div className={styles.viewAllRow}>
          <Link className={styles.viewAll} to={ROUTES.library}>
            View all courses →
          </Link>
        </div>
      )}
    </>
  );
}

/** The recent grid: recently-opened courses that aren't already in the continue section, as cover
 *  cards. Capped by the caller; the "View all" hatch lives below in HomeBody. */
function RecentCourses({
  courses,
  onRequestDelete,
}: {
  courses: CourseSummary[];
  onRequestDelete: (course: CourseSummary) => void;
}) {
  return (
    <section aria-labelledby="home-recent" className={styles.recent}>
      <h2 id="home-recent" className={styles.sectionTitle}>
        Recent courses
      </h2>
      <ul className={styles.grid}>
        {courses.map((course) => (
          <CourseCard key={course.id} course={course} onRequestDelete={onRequestDelete} />
        ))}
      </ul>
    </section>
  );
}

/** The Home dashboard at `/`: a greeting header over the learner's live state — the recent grid,
 *  the continue-learning hero, and the live-build banner (built up across Tasks 1–3). Reads the
 *  Phase 3 courses API via useLibrary; the composer now lives at /new. */
export function HomeDashboard({
  apiBaseUrl,
  userEmail,
  runs,
  onNewCourse,
  onResumeLesson,
  onViewCourse,
}: HomeDashboardProps) {
  const { state, reload } = useLibrary(apiBaseUrl);
  const deletion = useCourseDeletion(apiBaseUrl, reload);
  // Best-effort: the streak decorates the subline when it loads; a failure changes nothing.
  const { state: activityState } = useActivity(apiBaseUrl);
  const name = displayNameFromEmail(userEmail);
  const greeting = greetingForHour(new Date().getHours());

  return (
    <div className={styles.canvas}>
      <header className={styles.greeting}>
        <h2 className={styles.title}>
          Good {greeting}, {name}
        </h2>
        <p className={styles.subline}>{subline(state, activityState)}</p>
      </header>
      <LiveBuilds runs={runs} />
      <HomeBody
        apiBaseUrl={apiBaseUrl}
        state={state}
        reload={reload}
        onNewCourse={onNewCourse}
        onResumeLesson={onResumeLesson}
        onViewCourse={onViewCourse}
        onRequestDelete={deletion.request}
      />
      <ConfirmDialog
        open={deletion.pending !== null}
        title="Delete this course?"
        description={
          deletion.pending
            ? `“${deletion.pending.topic}” and everything about it — lessons, videos, your progress, bookmarks, and notes — will be permanently deleted. This can’t be undone.`
            : ""
        }
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        danger
        pending={deletion.isDeleting}
        errorMessage={deletion.error}
        onConfirm={deletion.confirm}
        onCancel={deletion.cancel}
      />
    </div>
  );
}
