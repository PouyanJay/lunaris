import { Link } from "react-router";

import { Badge } from "../primitives/Badge";
import { CourseCover } from "../primitives/CourseCover";
import { ProgressBar } from "../primitives/ProgressBar";
import { StatusDot } from "../primitives/StatusDot";
import { LEARNER_STATUS_META, LEVEL_LABELS } from "../../lib/courseLabels";
import { coverSeed } from "../../lib/coverSeed";
import { coursePath } from "../../lib/routes";
import type { CourseSummary } from "../../types/course";
import styles from "./CourseCard.module.css";

/** A cover card for one course summary — the shared unit of the My-courses grid and Home's recent
 *  grid: seeded constellation cover, title, "N lessons · Level" meta (+ a REVIEW badge when the
 *  build is unpublished), a determinate progress bar toned by status, and the house status dot.
 *  Renders its own `<li>` so it drops straight into a card `<ul>`; the whole card is one real link. */
export function CourseCard({ course }: { course: CourseSummary }) {
  const status = LEARNER_STATUS_META[course.learnerStatus];
  const meta = [
    `${course.lessonTotal} ${course.lessonTotal === 1 ? "lesson" : "lessons"}`,
    ...(course.level ? [LEVEL_LABELS[course.level]] : []),
  ].join(" · ");
  return (
    <li>
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
    </li>
  );
}
