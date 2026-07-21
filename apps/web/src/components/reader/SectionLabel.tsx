import styles from "./SectionLabel.module.css";

interface SectionLabelProps {
  /** The label word(s), lowered from the leading "LABEL:" of a prose section (colon dropped). */
  heading?: string;
  /** An optional "(qualifier)" that trailed the label, shown muted beside it. */
  qual?: string;
}

/** A lesson-section eyebrow: the leading "STRATEGY:" / "UPSTREAM LAYER (alarmins):" of a prose block,
 *  lifted into a small uppercase-mono accent label that opens the section. Carries heading semantics
 *  (aria-level 4, under the lesson h2 / phase h3) so the sections form a real document outline for
 *  assistive tech; the eyebrow styling is the visual layer only. */
export function SectionLabel({ heading, qual }: SectionLabelProps) {
  if (!heading) return null;
  return (
    <p className={styles.label} role="heading" aria-level={4}>
      <span className={styles.eyebrow}>{heading}</span>
      {qual ? <span className={styles.qual}>{qual}</span> : null}
    </p>
  );
}
