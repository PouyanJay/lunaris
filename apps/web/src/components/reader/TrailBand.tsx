import type { ReactNode } from "react";

import type { ActivityState } from "../../hooks/useActivity";
import { deriveTodayMinutes } from "../../lib/trailMinutes";
import styles from "./TrailBand.module.css";

interface TrailBandProps {
  activity: ActivityState;
  /** The learner's position in the course, 1-based. */
  lessonNumber: number;
  lessonTotal: number;
  /** Now, for today's studied-minutes lookup; injectable for deterministic tests. */
  now?: Date;
}

/** One labelled mono metric of the band (uppercase label + tabular value), with room for an
 *  adornment (the streak dot). */
function Metric({
  label,
  value,
  variant,
  children,
}: {
  label: string;
  value: ReactNode;
  variant?: "streak";
  children?: ReactNode;
}) {
  return (
    <span className={`${styles.metric} ${variant ? styles[variant] : ""}`.trim()}>
      {label} <span className={styles.value}>{value}</span>
      {children}
    </span>
  );
}

/** The Trail motivation band (Focus Flow phase 4): the stakes of learning, made visible while you
 *  study — the real current streak, the minutes studied today, and where you are in the course.
 *  Every value is a measured fact, not an invented score. Best-effort: absent on error, a skeleton
 *  while loading. The streak is the single accent. */
export function TrailBand({ activity, lessonNumber, lessonTotal, now }: TrailBandProps) {
  if (activity.status === "error") return null;

  if (activity.status === "loading") {
    return (
      <div className={styles.band} role="group" aria-label="Your progress" aria-busy="true">
        <span className={styles.skeleton} aria-hidden="true" />
      </div>
    );
  }

  const { currentStreak } = activity.view.stats;
  const minutesToday = deriveTodayMinutes(activity.view.heat, now ?? new Date());

  return (
    <div className={styles.band} role="group" aria-label="Your progress">
      <Metric
        label="Streak"
        variant="streak"
        value={`${currentStreak} ${currentStreak === 1 ? "day" : "days"}`}
      >
        {currentStreak > 0 && <span className={styles.streakDot} aria-hidden="true" />}
      </Metric>

      <Metric label="Today" value={`${minutesToday} min`} />

      <Metric label="Lesson" value={`${lessonNumber} of ${lessonTotal}`} />
    </div>
  );
}
