import { useState } from "react";
import { Link } from "react-router";

import { CourseCard } from "../course/CourseCard";
import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useLibrary } from "../../hooks/useLibrary";
import { LEARNER_STATUS_META } from "../../lib/courseLabels";
import { relativeTime } from "../../lib/relativeTime";
import { coursePath } from "../../lib/routes";
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
      <div className={styles.filters} role="group" aria-label="Filter courses">
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            className={styles.pill}
            aria-pressed={filter === value}
            onClick={() => onChange(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <span className={styles.sortNote}>Sorted by last opened ↓</span>
    </div>
  );
}

/** The amber live-build strip: one per RUNNING run, linking into the building course's canvas. */
function LiveBuildBanner({ run }: { run: CourseRun }) {
  return (
    <Link className={styles.banner} to={coursePath(run.id)}>
      <span className={styles.bannerPulse} aria-hidden="true" />
      <span className={styles.bannerBody}>
        <span className={styles.bannerTitle}>Building — {run.topic}</span>
        <span className={styles.bannerMeta}>Started {relativeTime(run.createdAt)}</span>
      </span>
      <span className={styles.bannerCta} aria-hidden="true">
        Open →
      </span>
    </Link>
  );
}

/** The My-courses library: counts subline, learner-status filter pills, the live-build banner,
 *  and a cover-card grid (title, "N lessons · Level", progress bar, status) sorted server-side
 *  by last opened. Renders all data states — a card-shaped loading skeleton, designed empty and
 *  filtered-empty notices, and a recoverable error. */
export function CourseLibrary({ apiBaseUrl, onNewCourse, runs = [] }: CourseLibraryProps) {
  const { state, reload } = useLibrary(apiBaseUrl);
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
      {runningRuns.map((run) => (
        <LiveBuildBanner key={run.runId} run={run} />
      ))}
      <LibraryFilterToolbar filter={filter} onChange={setFilter} />
      {visible.length === 0 && filter !== "all" ? (
        <p className={styles.filterEmpty}>{FILTER_EMPTY[filter]}</p>
      ) : (
        <ul className={styles.grid}>
          {visible.map((course) => (
            <CourseCard key={course.id} course={course} />
          ))}
        </ul>
      )}
    </div>
  );
}
