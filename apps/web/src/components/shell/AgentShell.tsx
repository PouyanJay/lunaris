import type { ReactNode } from "react";

import styles from "./AgentShell.module.css";

const CANVAS_ID = "agent-canvas";

interface AgentShellProps {
  /** The persistent left rail (brand, actions, run history, nav). */
  sidebar: ReactNode;
  /** Contextual title for the current canvas view. */
  title: string;
  /** Right-aligned canvas-header content — status, metrics, view actions. */
  meta?: ReactNode;
  children: ReactNode;
}

/** The two-pane instrument shell: a persistent left sidebar welded by a hairline to the canvas
 *  (a contextual header band over a full-bleed body). Panels, not floating cards; the lighter top
 *  edge gives the frame its light-from-above.
 *
 *  Intentionally separate from `AppFrame`, which serves the offline SeedApp (no sidebar, brand mark
 *  in its header) — merging them would entangle two brand placements and an optional rail into one
 *  component. */
export function AgentShell({ sidebar, title, meta, children }: AgentShellProps) {
  return (
    <div className={styles.shell}>
      <a className="skip-link" href={`#${CANVAS_ID}`}>
        Skip to content
      </a>
      <aside className={styles.sidebar} aria-label="Runs and navigation">
        {sidebar}
      </aside>
      <section className={styles.canvas}>
        <header className={styles.header}>
          <h1 className={styles.title} title={title}>
            {title}
          </h1>
          {meta && <div className={styles.meta}>{meta}</div>}
        </header>
        <main id={CANVAS_ID} className={styles.body}>
          {children}
        </main>
      </section>
    </div>
  );
}
