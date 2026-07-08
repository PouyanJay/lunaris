import type { ScorecardGauge } from "../../lib/instruments";
import styles from "./ReadinessScorecard.module.css";

interface ReadinessScorecardProps {
  gauges: ScorecardGauge[];
}

/** The readiness scorecard (P8): honest gauges only — each tile exists because its source event
 *  arrived, and its tone states a fact (claims cut, gaps found), never an invented gate. The
 *  caller hides the whole section while no gauge has a reading. */
export function ReadinessScorecard({ gauges }: ReadinessScorecardProps) {
  return (
    <section className={styles.panel} aria-label="Readiness scorecard">
      <p className={`eyebrow ${styles.title}`}>Readiness scorecard</p>
      <div className={styles.grid}>
        {gauges.map((gauge) => (
          <div key={gauge.key} className={styles.tile} data-tone={gauge.tone}>
            {gauge.pct !== null && (
              <svg
                className={styles.ring}
                viewBox="0 0 36 36"
                width="34"
                height="34"
                aria-hidden="true"
              >
                <circle className={styles.ringTrack} cx="18" cy="18" r="15.5" />
                <circle
                  className={styles.ringValue}
                  cx="18"
                  cy="18"
                  r="15.5"
                  strokeDasharray={`${(gauge.pct / 100) * 97.4} 97.4`}
                />
              </svg>
            )}
            <div className={styles.tileBody}>
              <div className={styles.tileHead}>
                <span className={styles.label}>{gauge.label}</span>
                <span className={`${styles.value} mono`}>{gauge.value}</span>
              </div>
              <div className={`${styles.detail} mono`}>{gauge.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
