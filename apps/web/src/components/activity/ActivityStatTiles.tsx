import type { ActivityStats } from "../../lib/activity";
import styles from "./ActivityStatTiles.module.css";

interface ActivityStatTilesProps {
  stats: ActivityStats;
}

/** The four headline figures. The current streak is the screen's ONE accent metric (the amber
 *  scalpel); the rest stay ink. All numerals are mono per the data-typography rule. */
export function ActivityStatTiles({ stats }: ActivityStatTilesProps) {
  return (
    <dl className={styles.grid}>
      <div className={styles.tile}>
        <dd className={`${styles.value} ${styles.accent}`}>{stats.currentStreak}</dd>
        <dt className={styles.label}>Current streak</dt>
      </div>
      <div className={styles.tile}>
        <dd className={styles.value}>{stats.longestStreak}</dd>
        <dt className={styles.label}>Longest streak</dt>
      </div>
      <div className={styles.tile}>
        <dd className={styles.value}>
          {stats.minutesThisWeek}
          <span className={styles.unit}>&nbsp;min</span>
        </dd>
        <dt className={styles.label}>This week</dt>
      </div>
      <div className={styles.tile}>
        <dd className={styles.value}>{stats.conceptsThisWeek}</dd>
        <dt className={styles.label}>Concepts this week</dt>
      </div>
    </dl>
  );
}
