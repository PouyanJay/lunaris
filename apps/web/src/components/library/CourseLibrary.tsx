import { Link } from "react-router";

import { CourseCover } from "../primitives/CourseCover";
import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useLibrary } from "../../hooks/useLibrary";
import { coverSeed } from "../../lib/coverSeed";
import { coursePath } from "../../lib/routes";
import type { CourseSummary } from "../../types/course";
import styles from "./CourseLibrary.module.css";

interface CourseLibraryProps {
  apiBaseUrl: string;
  /** Start a new course (the empty state's recovery action). */
  onNewCourse: () => void;
}

const SKELETON_CARDS = 6;

function LibraryCard({ course }: { course: CourseSummary }) {
  return (
    <li>
      <Link className={styles.card} to={coursePath(course.id)}>
        <div className={styles.cover} aria-hidden="true">
          <CourseCover seed={coverSeed(course.id)} />
        </div>
        <span className={styles.cardBody}>
          <span className={styles.cardTitle}>{course.topic}</span>
          <span className={styles.cardMeta}>
            {course.lessonTotal} {course.lessonTotal === 1 ? "lesson" : "lessons"}
          </span>
        </span>
      </Link>
    </li>
  );
}

/** The My-courses library: every built course as a cover card linking into its canvas. Renders
 *  all data states — a card-shaped loading skeleton, a designed empty state that routes to the
 *  composer, and a recoverable error. */
export function CourseLibrary({ apiBaseUrl, onNewCourse }: CourseLibraryProps) {
  const { state, reload } = useLibrary(apiBaseUrl);

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

  if (state.courses.length === 0) {
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

  return (
    <div className={styles.canvas}>
      <ul className={styles.grid}>
        {state.courses.map((course) => (
          <LibraryCard key={course.id} course={course} />
        ))}
      </ul>
    </div>
  );
}
