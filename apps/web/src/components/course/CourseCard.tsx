import { Link } from "react-router";

import { Badge } from "../primitives/Badge";
import { CourseCover } from "../primitives/CourseCover";
import { ProgressBar } from "../primitives/ProgressBar";
import { StatusDot } from "../primitives/StatusDot";
import { TrashIcon } from "../icons/TrashIcon";
import { LEARNER_STATUS_META, LEVEL_LABELS } from "../../lib/courseLabels";
import { coverSeed } from "../../lib/coverSeed";
import { coursePath } from "../../lib/routes";
import type { CourseSummary } from "../../types/course";
import styles from "./CourseCard.module.css";

interface CourseCardProps {
  course: CourseSummary;
  /** When set, the card shows a hover/focus-revealed recycle-bin button that asks to delete this
   *  course. Absent → no delete affordance (the card is link-only). */
  onRequestDelete?: (course: CourseSummary) => void;
}

/** A cover card for one course summary — the shared unit of the My-courses grid and Home's recent
 *  grid: seeded constellation cover, title, "N lessons · Level" meta (+ a REVIEW badge when the
 *  build is unpublished), a determinate progress bar toned by status, and the house status dot.
 *  Renders its own `<li>` so it drops straight into a card `<ul>`; the whole card is one real link.
 *  The optional delete button is a sibling of that link (never nested inside it — a button inside an
 *  anchor is invalid) and only appears on hover/focus. */
export function CourseCard({ course, onRequestDelete }: CourseCardProps) {
  const status = LEARNER_STATUS_META[course.learnerStatus];
  const meta = [
    `${course.lessonTotal} ${course.lessonTotal === 1 ? "lesson" : "lessons"}`,
    ...(course.level ? [LEVEL_LABELS[course.level]] : []),
  ].join(" · ");
  return (
    <li className={styles.item}>
      <Link className={styles.card} to={coursePath(course.id)}>
        <div className={styles.cover} aria-hidden="true">
          <CourseCover seed={coverSeed(course.id)} />
        </div>
        <span className={styles.cardBody}>
          <span className={styles.cardTitle}>{course.topic}</span>
          <span className={styles.cardMeta}>
            {meta}
            {course.courseStatus === "review" && (
              <Badge category="warning" className={styles.reviewBadge}>
                REVIEW
              </Badge>
            )}
          </span>
          <ProgressBar
            value={course.percent / 100}
            label={`${course.topic} progress`}
            tone={course.learnerStatus === "completed" ? "success" : "accent"}
          />
          <StatusDot label={status.label} tone={status.tone} />
        </span>
      </Link>
      {onRequestDelete && (
        <button
          type="button"
          className={styles.deleteButton}
          aria-label={`Delete course: ${course.topic}`}
          title="Delete course"
          onClick={() => onRequestDelete(course)}
        >
          <TrashIcon />
        </button>
      )}
    </li>
  );
}
