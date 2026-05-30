import styles from "./GraphLegend.module.css";

const TIERS = [1, 2, 3, 4, 5];

/** Reads the difficulty ramp and the goal/known markers used across the canvas. */
export function GraphLegend() {
  return (
    <div className={styles.legend} aria-label="Legend">
      <div className={styles.row}>
        <span className="eyebrow">Difficulty</span>
        <div className={styles.ramp} aria-hidden="true">
          {TIERS.map((tier) => (
            <span
              key={tier}
              className={styles.swatch}
              style={{ background: `var(--tier-${tier})` }}
            />
          ))}
        </div>
        <span className={`${styles.ends} mono`}>easier → harder</span>
      </div>
      <div className={styles.markers}>
        <span className={styles.marker}>
          <span className={`${styles.box} ${styles.goal}`} aria-hidden="true" />
          <span className={`${styles.markerLabel} mono`}>GOAL</span>
        </span>
        <span className={styles.marker}>
          <span className={`${styles.box} ${styles.known}`} aria-hidden="true" />
          <span className={`${styles.markerLabel} mono`}>KNOWN</span>
        </span>
      </div>
    </div>
  );
}
