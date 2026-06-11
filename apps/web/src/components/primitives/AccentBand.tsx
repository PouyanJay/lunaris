import type { ReactNode } from "react";

import styles from "./AccentBand.module.css";

interface AccentBandProps {
  /** Layout class for the band's content (row/column etc.) — the band owns only its identity. */
  className?: string | undefined;
  children: ReactNode;
}

/** The hairline-band-with-accent-rail shell shared by every standing-condition banner (Draft
 *  mode, keyless provisioning, on-device build): accent-soft tint, hairline bottom, 2px accent
 *  rail, house padding. One shell so the family can't drift; announced politely (role=status). */
export function AccentBand({ className, children }: AccentBandProps) {
  return (
    <aside
      className={className ? `${styles.band} ${className}` : styles.band}
      role="status"
      aria-live="polite"
    >
      {children}
    </aside>
  );
}
