import type { CSSProperties, ReactNode } from "react";

import type { ActivityState } from "../../hooks/useActivity";
import { deriveTodayXp } from "../../lib/trailXp";
import styles from "./TrailBand.module.css";

interface TrailBandProps {
  activity: ActivityState;
  /** The learner's position in the course, 1-based. */
  lessonNumber: number;
  lessonTotal: number;
  /** Now, for the today-XP window; injectable for deterministic tests. */
  now?: Date;
}

/** One labelled mono metric of the band (uppercase label + tabular value), with room for an
 *  adornment (the streak dot, the XP meter). */
function Metric({
  label,
  value,
  variant,
  children,
}: {
  label: string;
  value: ReactNode;
  variant?: "streak" | "xp";
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
 *  study — the real current streak, today's XP toward the day's goal (a display lens over the real
 *  event feed), and where you are in the course. Best-effort: absent on error, a skeleton while
 *  loading. The streak is the single accent. */
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
  const { earned, goal } = deriveTodayXp(activity.view.feed, now ?? new Date());
  const percent = Math.min(100, goal > 0 ? Math.round((earned / goal) * 100) : 0);
  const isGoalReached = earned >= goal;

  return (
    <div className={styles.band} role="group" aria-label="Your progress">
      <Metric
        label="Streak"
        variant="streak"
        value={`${currentStreak} ${currentStreak === 1 ? "day" : "days"}`}
      >
        {currentStreak > 0 && <span className={styles.streakDot} aria-hidden="true" />}
      </Metric>

      <Metric label="Today" variant="xp" value={`${earned} / ${goal} XP`}>
        <span
          className={styles.meter}
          role="progressbar"
          aria-label="Today's goal"
          aria-valuemin={0}
          aria-valuemax={goal}
          aria-valuenow={Math.min(earned, goal)}
          style={{ "--xp-fill": `${percent}%` } as CSSProperties}
        >
          <span className={styles.meterFill} data-reached={isGoalReached || undefined} />
        </span>
      </Metric>

      <Metric label="Lesson" value={`${lessonNumber} of ${lessonTotal}`} />
    </div>
  );
}
