import styles from "./LunarSpinner.module.css";

interface LunarSpinnerProps {
  /** Diameter in px. Defaults to 13 (the phase-header size); tool cards pass a smaller value. */
  size?: number;
  className?: string | undefined;
}

/** The Lunaris "working" mark: a small moon whose lit face waxes and wanes through its phases while
 *  the agent is busy — our own branded spinner (not a generic ring). Purely decorative
 *  (`aria-hidden`); always pair it with a text status so screen readers hear the state. Under
 *  `prefers-reduced-motion` the moon holds a static crescent instead of cycling. */
export function LunarSpinner({ size = 13, className }: LunarSpinnerProps) {
  return (
    <span
      className={`${styles.moon}${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
      data-testid="lunar-spinner"
    >
      <span className={styles.lit} />
    </span>
  );
}
