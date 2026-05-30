import styles from "./StatusDot.module.css";

export type StatusTone = "neutral" | "accent" | "success" | "warning" | "danger";

interface StatusDotProps {
  /** Uppercased automatically; rendered in mono per the house status convention. */
  label: string;
  tone?: StatusTone;
  /** Pulse the dot for genuinely live/running states only. */
  live?: boolean;
}

/** The house status convention: a small colored dot + an UPPERCASE MONO label in neutral
 *  text — never a saturated filled pill. */
export function StatusDot({ label, tone = "neutral", live = false }: StatusDotProps) {
  return (
    <span className={styles.root}>
      <span
        className={`${styles.dot} ${styles[tone]} ${live ? styles.live : ""}`}
        aria-hidden="true"
      />
      <span className={styles.label}>{label.toUpperCase()}</span>
    </span>
  );
}
