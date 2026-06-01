import { type CSSProperties, type ReactNode } from "react";

import {
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_RAIL_WIDTH,
  type SidebarLayout,
} from "../../hooks/useSidebarLayout";
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
  /** Collapse + resizable-width state for the rail (owned by the studio, see useSidebarLayout). */
  layout: SidebarLayout;
}

/** The two-pane instrument shell: a persistent left sidebar welded by a draggable hairline splitter
 *  to the canvas (a contextual header band over a full-bleed body). The rail collapses to a narrow
 *  icon rail and, when expanded, is resizable; collapsing/expanding eases the width, dragging tracks
 *  the cursor. Panels, not floating cards; the lighter top edge gives the frame its light-from-above.
 *
 *  Intentionally separate from `AppFrame`, which serves the offline SeedApp (no sidebar, brand mark
 *  in its header) — merging them would entangle two brand placements and an optional rail into one
 *  component. */
export function AgentShell({ sidebar, title, meta, children, layout }: AgentShellProps) {
  const { collapsed, width, resizing, startResize, nudgeWidth } = layout;
  const shellStyle = {
    "--sidebar-width": `${collapsed ? SIDEBAR_RAIL_WIDTH : width}px`,
  } as CSSProperties;

  return (
    <div className={styles.shell} style={shellStyle} data-resizing={resizing || undefined}>
      <a className="skip-link" href={`#${CANVAS_ID}`}>
        Skip to content
      </a>
      <aside className={styles.sidebar} aria-label="Runs and navigation">
        {sidebar}
      </aside>
      {!collapsed && (
        <div
          className={styles.resizer}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
          aria-valuenow={width}
          aria-valuemin={SIDEBAR_MIN_WIDTH}
          aria-valuemax={SIDEBAR_MAX_WIDTH}
          tabIndex={0}
          onPointerDown={startResize}
          onKeyDown={nudgeWidth}
          data-resizing={resizing || undefined}
        />
      )}
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
