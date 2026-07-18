import { useState } from "react";

import { CourseCard } from "../course/CourseCard";
import { DeleteCourseDialog } from "../course/DeleteCourseDialog";
import { FilterPills } from "../primitives/FilterPills";
import { LiveBuildBanner } from "../course/LiveBuildBanner";
import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useCourseDeletion } from "../../hooks/useCourseDeletion";
import { useLibrary } from "../../hooks/useLibrary";
import { LEARNER_STATUS_META } from "../../lib/courseLabels";
import type { CourseRun, CourseSummary, LearnerCourseStatus } from "../../types/course";
import styles from "./CourseLibrary.module.css";

interface CourseLibraryProps {
  apiBaseUrl: string;
  /** Start a new course (the empty state's recovery action). */
  onNewCourse: () => void;
  /** The run history (from the shell's useRuns) — RUNNING rows render the live-build banner. */
  runs?: CourseRun[];
}

type LibraryFilter = "all" | LearnerCourseStatus;

// One source of truth for the status wording: the pills reuse the shared card labels.
const FILTERS: { value: LibraryFilter; label: string }[] = [
  { value: "all", label: "All" },
  ...(Object.keys(LEARNER_STATUS_META) as LearnerCourseStatus[]).map((value) => ({
    value,
    label: LEARNER_STATUS_META[value].label,
  })),
];

/** What a filter with no matches should say — specific, never a silently blank grid (the pills
 *  themselves are the recovery path). */
const FILTER_EMPTY: Record<Exclude<LibraryFilter, "all">, string> = {
  in_progress: "Nothing in progress — open a course to pick it up.",
  completed: "No completed courses yet — finish a course and it lands here.",
  not_started: "No untouched courses — everything here has been started.",
};

const SKELETON_CARDS = 6;

/** How many leading cards load their cover eagerly at high priority — the first two grid rows
 *  (3-up desktop, 2-up mobile), which are above the fold; the rest stay lazy. */
const EAGER_COVER_COUNT = 6;

function countsLine(courses: CourseSummary[]): string {
  const counts = { in_progress: 0, completed: 0, not_started: 0 };
  for (const course of courses) counts[course.learnerStatus] += 1;
  const total = courses.length;
  return [
    `${total} ${total === 1 ? "course" : "courses"}`,
    `${counts.in_progress} in progress`,
    `${counts.completed} completed`,
    `${counts.not_started} not started`,
  ].join(" · ");
}

/** The learner-status pills + the sort note — the library's one piece of local view state. */
function LibraryFilterToolbar({
  filter,
  onChange,
}: {
  filter: LibraryFilter;
  onChange: (filter: LibraryFilter) => void;
}) {
  return (
    <div className={styles.toolbar}>
      <FilterPills options={FILTERS} value={filter} onChange={onChange} label="Filter courses" />
      <span className={styles.sortNote}>Sorted by last opened ↓</span>
    </div>
  );
}

/** The My-courses library: counts subline, learner-status filter pills, the live-build banner,
 *  and a cover-card grid (title, "N lessons · Level", progress bar, status) sorted server-side
 *  by last opened. Renders all data states — a card-shaped loading skeleton, designed empty and
 *  filtered-empty notices, and a recoverable error. */
export function CourseLibrary({ apiBaseUrl, onNewCourse, runs = [] }: CourseLibraryProps) {
  const { state, reload } = useLibrary(apiBaseUrl);
  const deletion = useCourseDeletion(apiBaseUrl, reload);
  const [filter, setFilter] = useState<LibraryFilter>("all");
  const runningRuns = runs.filter((run) => run.status === "running");

  if (state.status === "loading") {
    return (
      <div className={styles.canvas}>
        <ul className={styles.grid} aria-busy="true" aria-label="Loading courses">
          {Array.from({ length: SKELETON_CARDS }, (_, index) => (
            <li key={index} className={styles.skeletonCard} />
          ))}
        </ul>
      </div>
    );
  }

  if (state.status === "error") {
    return <ErrorState eyebrow="Library" message={state.message} onRetry={reload} />;
  }

  if (state.courses.length === 0 && runningRuns.length === 0) {
    return (
      <CanvasNotice
        eyebrow="Library"
        title="No courses yet"
        body="Name a topic and the agent builds your first course — it will land here."
        actionLabel="New course"
        onAction={onNewCourse}
      />
    );
  }

  const visible =
    filter === "all"
      ? state.courses
      : state.courses.filter((course) => course.learnerStatus === filter);

  return (
    <div className={styles.canvas}>
      <p className={styles.subline}>{countsLine(state.courses)}</p>
      {runningRuns.length > 0 && (
        <div className={styles.banners}>
          {runningRuns.map((run) => (
            <LiveBuildBanner key={run.runId} run={run} />
          ))}
        </div>
      )}
      <LibraryFilterToolbar filter={filter} onChange={setFilter} />
      {visible.length === 0 && filter !== "all" ? (
        <p className={styles.filterEmpty}>{FILTER_EMPTY[filter]}</p>
      ) : (
        <ul className={styles.grid}>
          {visible.map((course, index) => (
            <CourseCard
              key={course.id}
              course={course}
              onRequestDelete={deletion.request}
              // The first two rows (3-up desktop / 2-up mobile) load eagerly at high priority so the
              // above-the-fold covers paint immediately; the rest stay lazy.
              priority={index < EAGER_COVER_COUNT}
            />
          ))}
        </ul>
      )}
      <DeleteCourseDialog deletion={deletion} />
    </div>
  );
}
