import { useCourseProgress } from "../../hooks/useCourseProgress";
import { bucketLevel } from "../../lib/courseLevel";
import { coverSeed } from "../../lib/coverSeed";
import { flattenLessons } from "../../lib/flattenLessons";
import { lessonStateFor, type LessonState } from "../../lib/lessonState";
import type { CourseProgress, ProgressSummary } from "../../lib/progress";
import type { Course, CourseLevel, Lesson } from "../../types/course";
import { LessonChip } from "../course/LessonChip";
import { Button } from "../primitives/Button";
import { CourseCover } from "../primitives/CourseCover";
import { ProgressBar } from "../primitives/ProgressBar";
import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import { ScopeBand } from "../reader/ScopeBand";
import styles from "./CourseOverview.module.css";

interface CourseOverviewProps {
  course: Course;
  /** The API origin for the learner's progress; absent/empty (offline) hides progress chrome. */
  apiBaseUrl?: string | undefined;
  /** Open the reader — at the resume lesson when one is known. */
  onContinue: (lessonId?: string) => void;
  /** Jump to the prerequisite-graph explorer. */
  onViewMap: () => void;
  /** Open the reader focused on one lesson (a row click). */
  onOpenLesson: (lessonId: string) => void;
  /** Ask to delete this course (opens the confirm dialog). Absent → no delete affordance. */
  onDelete?: (() => void) | undefined;
}

/** One Overview row: a lesson in course order with its owning module's title, plus the module's
 *  objectives count on module-start rows (mirroring where the reader shows them). */
interface OverviewRow {
  lesson: Lesson;
  number: number;
  moduleTitle: string;
  objectiveCount: number | null;
}

function buildRows(course: Course): OverviewRow[] {
  return flattenLessons(course).map((flat) => ({
    lesson: flat.lesson,
    number: flat.index + 1,
    moduleTitle: flat.module.title,
    objectiveCount: flat.isFirstInModule ? flat.module.objectives.length : null,
  }));
}

const ROW_STATE_META: Record<LessonState, { label: string; tone: StatusTone }> = {
  done: { label: "Done", tone: "success" },
  in_progress: { label: "In progress", tone: "accent" },
  up_next: { label: "Up next", tone: "neutral" },
};

/** Resume where the learner left off; else the first unfinished lesson. Without a snapshot there
 *  is nothing to resume from — the reader opens at its own default. */
function resolveResumeLessonId(
  rows: OverviewRow[],
  progress: CourseProgress | null,
  stateFor: (lessonId: string) => LessonState,
): string | undefined {
  const recordedPosition =
    progress?.lastLessonId && rows.some((row) => row.lesson.id === progress.lastLessonId)
      ? progress.lastLessonId
      : undefined;
  const firstUnfinished = progress
    ? rows.find((row) => stateFor(row.lesson.id) !== "done")?.lesson.id
    : undefined;
  return recordedPosition ?? firstUnfinished;
}

interface LessonRowProps {
  row: OverviewRow;
  state: LessonState;
  onOpen: () => void;
}

function LessonRow({ row, state, onOpen }: LessonRowProps) {
  const meta = ROW_STATE_META[state];
  const objectives =
    row.objectiveCount !== null && row.objectiveCount > 0
      ? ` · ${row.objectiveCount} ${row.objectiveCount === 1 ? "objective" : "objectives"}`
      : "";
  return (
    <li>
      <button type="button" className={styles.row} onClick={onOpen}>
        <LessonChip number={row.number} state={state} />
        <span className={styles.rowBody}>
          <span className={styles.rowTitle}>{row.moduleTitle}</span>
          <span className={styles.rowMeta}>
            Lesson {row.number}
            {objectives}
          </span>
        </span>
        <StatusDot label={meta.label} tone={meta.tone} />
        <span className={styles.chevron} aria-hidden="true">
          ›
        </span>
      </button>
    </li>
  );
}

interface OverviewHeroProps {
  course: Course;
  lessonTotal: number;
  level: CourseLevel | null;
  summary: ProgressSummary | null;
  resumeLessonId: string | undefined;
  onContinue: (lessonId?: string) => void;
  onViewMap: () => void;
}

function OverviewHero({
  course,
  lessonTotal,
  level,
  summary,
  resumeLessonId,
  onContinue,
  onViewMap,
}: OverviewHeroProps) {
  const conceptTotal = course.graph.nodes.length;
  return (
    <section className={styles.hero}>
      <div className={styles.cover} aria-hidden="true">
        <CourseCover seed={coverSeed(course.id)} />
      </div>
      <div className={styles.heroBody}>
        <p className={styles.counts}>
          {lessonTotal} {lessonTotal === 1 ? "lesson" : "lessons"} · {conceptTotal}{" "}
          {conceptTotal === 1 ? "concept" : "concepts"}
          {level && <span className={styles.levelPill}>{level.toUpperCase()}</span>}
        </p>
        <h2 className={styles.title}>{course.topic}</h2>
        {summary && (
          <div className={styles.progressRow}>
            <div className={styles.progressTrack}>
              <ProgressBar
                value={summary.percent / 100}
                label={`${course.topic} progress`}
                tone={summary.percent === 100 ? "success" : "accent"}
              />
            </div>
            <span className={styles.progressLabel}>
              {summary.lessonsDone} of {summary.lessonTotal}{" "}
              {summary.lessonTotal === 1 ? "lesson" : "lessons"} · {summary.percent}%
            </span>
          </div>
        )}
        <div className={styles.actions}>
          <Button variant="accent" onClick={() => onContinue(resumeLessonId)}>
            Continue learning
          </Button>
          <Button onClick={onViewMap}>View the map</Button>
        </div>
      </div>
    </section>
  );
}

/** The course's landing tab, per the Lunaris Unified design: a hero (cover, counts + level pill,
 *  title, progress, Continue/View-the-map CTAs), the honest scope band when the build computed
 *  one, and the numbered lesson rows deep-linking into the reader. Progress is best-effort —
 *  offline, the facts and rows render without progress chrome. */
export function CourseOverview({
  course,
  apiBaseUrl,
  onContinue,
  onViewMap,
  onOpenLesson,
  onDelete,
}: CourseOverviewProps) {
  const { progress } = useCourseProgress(apiBaseUrl ?? "", course.id);
  const rows = buildRows(course);

  const stateFor = (lessonId: string): LessonState => lessonStateFor(progress, lessonId);

  return (
    <div className={styles.canvas}>
      <div className={styles.content}>
        <OverviewHero
          course={course}
          lessonTotal={rows.length}
          level={bucketLevel(course.graph.nodes)}
          summary={progress?.summary ?? null}
          resumeLessonId={resolveResumeLessonId(rows, progress, stateFor)}
          onContinue={onContinue}
          onViewMap={onViewMap}
        />
        {course.scope && <ScopeBand scope={course.scope} />}
        <section aria-label="Lessons">
          <p className={`eyebrow ${styles.lessonsEyebrow}`}>Lessons</p>
          <ul className={styles.rows}>
            {rows.map((row) => (
              <LessonRow
                key={row.lesson.id}
                row={row}
                state={stateFor(row.lesson.id)}
                onOpen={() => onOpenLesson(row.lesson.id)}
              />
            ))}
          </ul>
        </section>
        {onDelete && (
          <section className={styles.danger} aria-label="Delete course">
            <div className={styles.dangerText}>
              <p className="eyebrow">Danger zone</p>
              <p className={styles.dangerBody}>
                Deleting removes this course and everything about it — lessons, videos, your
                progress, bookmarks, and notes. This can’t be undone.
              </p>
            </div>
            <Button variant="danger" onClick={onDelete}>
              Delete course
            </Button>
          </section>
        )}
      </div>
    </div>
  );
}
