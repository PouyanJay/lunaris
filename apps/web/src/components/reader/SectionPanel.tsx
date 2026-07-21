import type { ReactNode } from "react";

import styles from "./SectionPanel.module.css";

/** A bordered panel wrapping a worked-example / worked-attribution section (its eyebrow label plus
 *  body), setting the concrete instance apart from the surrounding explanation. A plain <section>
 *  (no landmark role) — the eyebrow inside already heads it. */
export function SectionPanel({ children }: { children?: ReactNode }) {
  return <section className={styles.panel}>{children}</section>;
}
