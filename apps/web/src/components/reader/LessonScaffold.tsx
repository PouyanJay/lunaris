import styles from "./LessonScaffold.module.css";

interface LessonScaffoldProps {
  /** The bookend's title, e.g. "What this lesson expects" / "Self-check". */
  title: string;
  /** A one-line plain-language cue under the title. */
  cue: string;
  /** The scaffolding lines — entry expectations or self-assessment prompts. */
  items: string[];
}

/** A lesson-arc bookend (P7.3): the "what this lesson expects" entry list or the closing "self-check"
 *  prompts, rendered as a subtle hairline panel — scaffolding the learner reads, visually distinct
 *  from the teaching phases it brackets. `items` is expected non-empty (the caller guards, so a
 *  pre-P7.3 course omits the panel). */
export function LessonScaffold({ title, cue, items }: LessonScaffoldProps) {
  return (
    <section className={styles.panel} aria-label={title}>
      <div className={styles.head}>
        <h3 className={styles.title}>{title}</h3>
        <p className={styles.cue}>{cue}</p>
      </div>
      <ul className={styles.list}>
        {/* Stable, non-reordered list → index keys are safe. */}
        {items.map((item, index) => (
          <li key={index} className={styles.item}>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}
