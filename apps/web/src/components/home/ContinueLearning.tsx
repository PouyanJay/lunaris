import { Link } from "react-router";

import { Button } from "../primitives/Button";
import { CourseCover } from "../primitives/CourseCover";
import { ProgressBar } from "../primitives/ProgressBar";
import { useContinueLearning, type ContinueState } from "../../hooks/useContinueLearning";
import { coverSeed } from "../../lib/coverSeed";
import { CONTINUE_ROW_LIMIT } from "../../lib/homeCourses";
import { coursePath } from "../../lib/routes";
import type { CourseSummary } from "../../types/course";
import styles from "./ContinueLearning.module.css";

interface ContinueLearningProps {
  apiBaseUrl: string;
  /** In-progress courses, last-opened first — the first is the hero, the rest compact rows. */
  inProgress: CourseSummary[];
  /** Resume into the reader — at the resume lesson when known, else its Overview picks the spot. */
  onResume: (courseId: string, lessonId?: string) => void;
  /** Open the course's Overview tab. */
  onViewCourse: (courseId: string) => void;
}

function lessonsLabel(course: CourseSummary): string {
  const unit = course.lessonTotal === 1 ? "lesson" : "lessons";
  return `${course.lessonsDone} of ${course.lessonTotal} ${unit} · ${course.percent}%`;
}

/** The resume position line: "Lesson N of M · module" once the course loads, a stable muted
 *  placeholder while it's in flight (so the hero never shifts), and nothing on error. */
function PositionLine({ state }: { state: ContinueState | null }) {
  if (!state || state.status === "loading") {
    return (
      <p className={styles.position}>
        <span className={styles.positionMuted}>Finding where you left off…</span>
      </p>
    );
  }
  if (state.status === "error" || !state.resume) {
    return <p className={styles.position} />;
  }
  const { number, total, moduleTitle } = state.resume;
  return (
    <p className={styles.position}>
      <span className="mono">
        Lesson {number} of {total}
      </span>
      {` · ${moduleTitle}`}
    </p>
  );
}

function ContinueHero({
  course,
  state,
  onResume,
  onViewCourse,
}: {
  course: CourseSummary;
  state: ContinueState | null;
  onResume: (courseId: string, lessonId?: string) => void;
  onViewCourse: (courseId: string) => void;
}) {
  const resumeLessonId = state?.status === "ready" ? state.resume?.lessonId : undefined;
  return (
    <section className={styles.hero}>
      <div className={styles.cover} aria-hidden="true">
        <CourseCover seed={coverSeed(course.id)} />
      </div>
      <div className={styles.heroBody}>
        <h3 className={styles.heroTitle}>{course.topic}</h3>
        <PositionLine state={state} />
        <div className={styles.progressRow}>
          <div className={styles.progressTrack}>
            <ProgressBar
              value={course.percent / 100}
              label={`${course.topic} progress`}
              tone="accent"
            />
          </div>
          <span className={styles.progressLabel}>{lessonsLabel(course)}</span>
        </div>
        <div className={styles.actions}>
          <Button
            variant="accent"
            onClick={() =>
              resumeLessonId ? onResume(course.id, resumeLessonId) : onViewCourse(course.id)
            }
          >
            Resume lesson
          </Button>
          <Button onClick={() => onViewCourse(course.id)}>View course</Button>
        </div>
      </div>
    </section>
  );
}

function InProgressRow({ course }: { course: CourseSummary }) {
  return (
    <li>
      <Link className={styles.row} to={coursePath(course.id)}>
        <div className={styles.rowCover} aria-hidden="true">
          <CourseCover seed={coverSeed(course.id)} />
        </div>
        <span className={styles.rowBody}>
          <span className={styles.rowTitle}>{course.topic}</span>
          <span className={styles.rowMeta}>{lessonsLabel(course)}</span>
        </span>
        <div className={styles.rowTrack}>
          <ProgressBar
            value={course.percent / 100}
            label={`${course.topic} progress`}
            tone="accent"
          />
        </div>
        <span className={styles.chevron} aria-hidden="true">
          ›
        </span>
      </Link>
    </li>
  );
}

/** Home's continue-learning section: the most-recent in-progress course as a hero (cover,
 *  "Lesson N of M", next-up line, progress, Resume/View) plus compact rows for the other
 *  in-progress courses. Renders nothing when nothing is in progress. */
export function ContinueLearning({
  apiBaseUrl,
  inProgress,
  onResume,
  onViewCourse,
}: ContinueLearningProps) {
  const hero = inProgress[0] ?? null;
  const state = useContinueLearning(apiBaseUrl, hero?.id ?? null);
  if (!hero) return null;

  const rows = inProgress.slice(1, 1 + CONTINUE_ROW_LIMIT);
  return (
    <section aria-labelledby="home-continue" className={styles.section}>
      <h2 id="home-continue" className={`eyebrow ${styles.sectionEyebrow}`}>
        Continue learning
      </h2>
      <ContinueHero
        course={hero}
        state={state}
        onResume={onResume}
        onViewCourse={onViewCourse}
      />
      {rows.length > 0 && (
        <ul className={styles.rows}>
          {rows.map((course) => (
            <InProgressRow key={course.id} course={course} />
          ))}
        </ul>
      )}
    </section>
  );
}
