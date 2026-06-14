import styles from "./OutdatedBadge.module.css";

/** The "outdated" signal on a built video whose lesson has since been revised (explainer-video
 *  V6-T3): a muted warning dot + an UPPERCASE-MONO status label, paired with the regenerate menu
 *  that resolves it. A badge only — staleness never auto-regenerates (cost stays user-controlled). */
export function OutdatedBadge() {
  return (
    <span className={styles.badge} role="status">
      <span className={styles.dot} aria-hidden="true" />
      <span className={styles.label}>OUTDATED</span>
      <span className={styles.hint}>the lesson changed — regenerate to update</span>
    </span>
  );
}
