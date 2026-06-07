import styles from "./WorkedExample.module.css";

/** One labelled side of a worked example — the label (e.g. "Literal", "With collocation") and the
 *  phrasing it names. Decoupled from the wire `TransformSide` so the prose-pattern lift and the typed
 *  spec can both feed the same view. */
export interface WorkedExampleSide {
  label: string;
  text: string;
}

interface WorkedExampleProps {
  literal: WorkedExampleSide;
  improved: WorkedExampleSide;
  /** Why the rewrite is better (register, tone, precision) — omitted when there's nothing to add. */
  note: string | null;
}

/** A worked example rendered as its own panel: the literal/naive phrasing beside its improved rewrite
 *  — shown together, because the contrast is the teaching point — with a note explaining why the
 *  rewrite is better. Shared by the typed `worked-example` visual and the prose-pattern lift so both
 *  read identically. Composed as one hairline-divided panel (no nested cards); the accent is the
 *  scalpel — only the improved side carries it (a soft tint + accented label), and the labels carry
 *  the meaning so the distinction never rests on colour alone (WCAG). */
export function WorkedExample({ literal, improved, note }: WorkedExampleProps) {
  return (
    <div className={styles.example}>
      <div className={styles.pair}>
        <section className={styles.side} aria-label={literal.label}>
          <p className={`mono ${styles.label}`}>{literal.label}</p>
          <p className={styles.text}>{literal.text}</p>
        </section>
        <section className={`${styles.side} ${styles.improved}`} aria-label={improved.label}>
          <p className={`mono ${styles.label}`}>{improved.label}</p>
          <p className={styles.text}>{improved.text}</p>
        </section>
      </div>
      {note ? (
        <p className={styles.note}>
          <span className={`mono ${styles.noteMark}`}>Why</span>
          <span>{note}</span>
        </p>
      ) : null}
    </div>
  );
}
