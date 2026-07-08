import styles from "./GraphLegend.module.css";

const TIERS = [1, 2, 3, 4, 5];

/** Reads the difficulty ramp and the learning-state key used across the canvas: the mastered /
 *  up-next dots mirror the node badges, the goal ring mirrors the goal node's accent ring. */
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
          <span className={`${styles.dot} ${styles.mastered}`} aria-hidden="true" />
          <span className={`${styles.markerLabel} mono`}>mastered</span>
        </span>
        <span className={styles.marker}>
          <span className={`${styles.dot} ${styles.upNext}`} aria-hidden="true" />
          <span className={`${styles.markerLabel} mono`}>up next</span>
        </span>
        <span className={styles.marker}>
          <span className={`${styles.box} ${styles.goal}`} aria-hidden="true" />
          <span className={`${styles.markerLabel} mono`}>goal</span>
        </span>
      </div>
    </div>
  );
}
