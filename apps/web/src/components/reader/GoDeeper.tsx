import type { ReactNode } from "react";

import styles from "./GoDeeper.module.css";

interface GoDeeperProps {
  /** The authored fold label (`:::deeper[label]`), shown beside the kicker. */
  label?: string;
  children?: ReactNode;
}

/** A depth fold (Field Guide): rigor the main reading path doesn't need, collapsed behind a native
 *  `<details>` under a mono "Go deeper" kicker. Inherits the markdown layer's details panel and
 *  summary affordances (marker, focus ring), so it stays consistent with `:::details`. */
export function GoDeeper({ label, children }: GoDeeperProps) {
  return (
    <details>
      <summary>
        <span className={styles.kicker}>Go deeper</span>
        {label}
      </summary>
      {children}
    </details>
  );
}
