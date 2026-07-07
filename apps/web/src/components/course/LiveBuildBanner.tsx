import { Link } from "react-router";

import { relativeTime } from "../../lib/relativeTime";
import { coursePath } from "../../lib/routes";
import type { CourseRun } from "../../types/course";
import styles from "./LiveBuildBanner.module.css";

/** The one amber-wash strip for a genuinely live build (My-courses + Home): a pulsing dot, the
 *  topic, when it started, and a link into the building course's canvas. The whole strip is one
 *  real link named by the topic; `cta` is decorative (aria-hidden). */
export function LiveBuildBanner({ run, cta = "Open →" }: { run: CourseRun; cta?: string }) {
  return (
    <Link className={styles.banner} to={coursePath(run.id)}>
      <span className={styles.pulse} aria-hidden="true" />
      <span className={styles.body}>
        <span className={styles.title}>Building — {run.topic}</span>
        <span className={styles.meta}>Started {relativeTime(run.createdAt)}</span>
      </span>
      <span className={styles.cta} aria-hidden="true">
        {cta}
      </span>
    </Link>
  );
}
