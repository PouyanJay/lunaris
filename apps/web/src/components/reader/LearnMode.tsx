import styles from "./LearnMode.module.css";

/** The guided Learn mode (Focus Flow): the lesson as a sequence of one-idea steps with a visible
 *  finish line. Walking-skeleton shell — the step model, card, and navigation land next. */
export function LearnMode() {
  return (
    <section className={styles.stage} aria-label="Lesson steps">
      <div className={styles.metrics}>
        <p className={styles.metric}>Step 1 of 1</p>
      </div>
    </section>
  );
}
