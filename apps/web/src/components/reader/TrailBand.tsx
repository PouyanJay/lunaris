import type { CSSProperties } from "react";

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
  const reached = earned >= goal;

  return (
    <div className={styles.band} role="group" aria-label="Your progress">
      <span className={`${styles.metric} ${styles.streak}`}>
        Streak
        <span className={styles.value}>
          {currentStreak} {currentStreak === 1 ? "day" : "days"}
        </span>
        {currentStreak > 0 && <span className={styles.streakDot} aria-hidden="true" />}
      </span>

      <span className={`${styles.metric} ${styles.xp}`}>
        <span>
          Today{" "}
          <span className={styles.value}>
            {earned} / {goal} XP
          </span>
        </span>
        <span
          className={styles.meter}
          role="progressbar"
          aria-label="Today's goal"
          aria-valuemin={0}
          aria-valuemax={goal}
          aria-valuenow={Math.min(earned, goal)}
          style={{ "--xp-fill": `${percent}%` } as CSSProperties}
        >
          <span className={styles.meterFill} data-reached={reached || undefined} />
        </span>
      </span>

      <span className={styles.metric}>
        Lesson{" "}
        <span className={styles.value}>
          {lessonNumber} of {lessonTotal}
        </span>
      </span>
    </div>
  );
}
