import type { ReactNode } from "react";

import styles from "./ExamplePanel.module.css";

/** A worked-example quotation lifted out of the prose into its own panel — an info icon, italic text,
 *  and an accent tint set it apart as "here is the concrete example" without breaking the sentence
 *  that introduced it (the lead-in stays above, the continuation below). */
export function ExamplePanel({ children }: { children?: ReactNode }) {
  return (
    <aside className={styles.panel} aria-label="Example">
      <span className={styles.icon} aria-hidden="true">
        ⓘ
      </span>
      <p className={styles.quote}>{children}</p>
    </aside>
  );
}
