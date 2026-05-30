import type { ReactNode } from "react";

import styles from "./AppFrame.module.css";

const MAIN_CONTENT_ID = "graph-body";

interface AppFrameProps {
  title: string;
  /** Right-aligned header content — status + metric band. */
  meta?: ReactNode;
  children: ReactNode;
}

/** The app instrument frame: a lighter top edge (light-from-above), a hairline-divided
 *  header band, and a full-bleed body. Panels, not floating cards. */
export function AppFrame({ title, meta, children }: AppFrameProps) {
  return (
    <div className={styles.frame}>
      <a className="skip-link" href={`#${MAIN_CONTENT_ID}`}>
        Skip to graph
      </a>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div className={styles.heading}>
            <span className="eyebrow">Lunaris · Prerequisite graph</span>
            <h1 className={styles.title} title={title}>
              {title}
            </h1>
          </div>
        </div>
        {meta && <div className={styles.meta}>{meta}</div>}
      </header>
      <main id={MAIN_CONTENT_ID} className={styles.body}>
        {children}
      </main>
    </div>
  );
}
