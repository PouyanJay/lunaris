import type { CourseScope } from "../../types/course";
import styles from "./ScopeBand.module.css";

interface ScopeBandProps {
  scope: CourseScope;
}

interface ScopeColumnProps {
  title: string;
  glyph: string;
  items: string[];
}

// The lists carry meaning by their heading + glyph SHAPE (✓ vs ✕), never colour — see ScopeBand.
const DELIVERS_GLYPH = "✓";
const EXCLUDES_GLYPH = "✕";

function ScopeColumn({ title, glyph, items }: ScopeColumnProps) {
  if (items.length === 0) return null;
  return (
    <div className={styles.column} role="group" aria-label={title}>
      <p className={styles.columnTitle}>{title}</p>
      <ul className={styles.list}>
        {/* Index keys are safe: the lines are agent-emitted and never reordered. */}
        {items.map((item, index) => (
          <li key={index} className={styles.item}>
            <span className={styles.glyph} aria-hidden="true">
              {glyph}
            </span>
            <span className={styles.itemText}>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The scope-realism header band (CQ Phase 3.1): an honest, at-a-glance framing of a course — how
 *  much effort it takes, and explicitly what it does and does not get you. A hairline-divided panel
 *  at the top of the reader; the effort is mono (the data layer) and the two lists are split by a
 *  text heading so the does/doesn't distinction never depends on colour. */
export function ScopeBand({ scope }: ScopeBandProps) {
  return (
    <section className={styles.band} aria-label="Course scope">
      <div className={styles.head}>
        <p className={styles.eyebrow}>Course scope</p>
        {scope.effort && <p className={`${styles.effort} mono`}>{scope.effort}</p>}
      </div>
      <div className={styles.columns}>
        <ScopeColumn title="What you'll get" glyph={DELIVERS_GLYPH} items={scope.delivers} />
        <ScopeColumn title="What it won't" glyph={EXCLUDES_GLYPH} items={scope.excludes} />
      </div>
    </section>
  );
}
