import type { ReactNode } from "react";

import styles from "./KeyedList.module.css";

/** A definition list lifted from a run of token-led sentences ("IL-4 drives…", "IL-5 recruits…").
 *  Real <dl>/<dt>/<dd> semantics pair each key with its definition for assistive tech. */
export function KeyedList({ children }: { children?: ReactNode }) {
  return <dl className={styles.list}>{children}</dl>;
}

/** One keyed row: a monospace key chip and its definition. Emitted as a fragment so <dt>/<dd> stay
 *  direct children of the <dl> (semantics require it). */
export function KeyedRow({ term, children }: { term?: string; children?: ReactNode }) {
  return (
    <>
      <dt className={styles.term}>
        <span className={`${styles.key} mono`}>{term}</span>
      </dt>
      <dd className={styles.def}>{children}</dd>
    </>
  );
}
