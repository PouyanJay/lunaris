import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { useEscapeKey } from "../../hooks/useEscapeKey";
import {
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_RAIL_WIDTH,
  type SidebarLayout,
} from "../../hooks/useSidebarLayout";
import { FOCUSABLE_SELECTOR } from "../../lib/focusable";
import styles from "./AgentShell.module.css";

const CANVAS_ID = "agent-canvas";
const SIDEBAR_ID = "agent-sidebar";

interface AgentShellProps {
  /** The persistent left rail (brand, actions, run history, nav). */
  sidebar: ReactNode;
  /** Contextual title for the current canvas view. */
  title: string;
  /** Right-aligned canvas-header content — status, metrics, view actions. */
  meta?: ReactNode;
  /** The global-search trigger, docked between the title and the meta (the ⌘K field). */
  search?: ReactNode;
  /** Optional secondary row under the header (e.g. a course's view tabs) — keeps the title row
   *  uncluttered. Hairline-divided from the header and the body. */
  toolbar?: ReactNode;
  /** Optional band rendered between the header and the body (e.g. the Draft-mode banner). */
  banner?: ReactNode;
  children: ReactNode;
  /** Collapse + resizable-width state for the rail (owned by the studio, see useSidebarLayout). */
  layout: SidebarLayout;
  /** Whether the sidebar is open as a mobile drawer (phone breakpoint). */
  mobileNavOpen: boolean;
  /** Open / close the mobile nav drawer (owned by the studio so nav actions can close it). */
  onOpenMobileNav: () => void;
  /** Close the mobile nav drawer (Esc, scrim tap, or a nav action). */
  onCloseMobileNav: () => void;
}

/** The two-pane instrument shell: a persistent left sidebar welded by a draggable hairline splitter
 *  to the canvas (a contextual header band over a full-bleed body). On desktop the rail collapses to
 *  a narrow icon rail and, when expanded, is resizable. On phones (≤768px) the rail goes off-canvas
 *  and opens as a focus-trapped drawer from the header's menu button — content gets the full width.
 *  Panels, not floating cards; the lighter top edge gives the frame its light-from-above.
 *
 *  Intentionally separate from `AppFrame`, which serves the offline SeedApp (no sidebar, brand mark
 *  in its header) — merging them would entangle two brand placements and an optional rail into one
 *  component. */
export function AgentShell({
  sidebar,
  title,
  meta,
  search,
  toolbar,
  banner,
  children,
  layout,
  mobileNavOpen,
  onOpenMobileNav,
  onCloseMobileNav,
}: AgentShellProps) {
  const { collapsed, width, resizing, startResize, nudgeWidth } = layout;
  const shellStyle = {
    "--sidebar-width": `${collapsed ? SIDEBAR_RAIL_WIDTH : width}px`,
  } as CSSProperties;

  const asideRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEscapeKey(mobileNavOpen, onCloseMobileNav);

  // While the drawer is open: lock body scroll, move focus into the rail, trap Tab within it, and
  // restore focus to the menu button on close — the WCAG modal-drawer contract (mirrors ConfirmDialog).
  useEffect(() => {
    if (!mobileNavOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const menuButton = menuButtonRef.current;
    const restoreTo = document.activeElement as HTMLElement | null;
    asideRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();

    // Trap Tab within the rail. Capture phase (like ConfirmDialog/VideoLightbox) so it wins over any
    // page-level key shortcuts and the contract is implemented identically across overlays.
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = asideRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      const first = items?.[0];
      const last = items?.[items.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown, true);
      (restoreTo ?? menuButton)?.focus();
    };
  }, [mobileNavOpen]);

  return (
    <div className={styles.shell} style={shellStyle} data-resizing={resizing || undefined}>
      <a className="skip-link" href={`#${CANVAS_ID}`}>
        Skip to content
      </a>
      <aside
        ref={asideRef}
        id={SIDEBAR_ID}
        className={styles.sidebar}
        aria-label="Runs and navigation"
        data-drawer-open={mobileNavOpen || undefined}
      >
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
          <button
            ref={menuButtonRef}
            type="button"
            className={styles.menuButton}
            aria-label="Open navigation"
            aria-controls={SIDEBAR_ID}
            aria-expanded={mobileNavOpen}
            onClick={onOpenMobileNav}
          >
            <MenuIcon />
          </button>
          <h1 className={styles.title} title={title}>
            {title}
          </h1>
          {search && <div className={styles.search}>{search}</div>}
          {meta && <div className={styles.meta}>{meta}</div>}
        </header>
        {toolbar && <div className={styles.toolbar}>{toolbar}</div>}
        {banner}
        <main id={CANVAS_ID} className={styles.body}>
          {children}
        </main>
      </section>
      {mobileNavOpen && (
        <button
          type="button"
          className={styles.scrim}
          aria-label="Close navigation"
          onClick={onCloseMobileNav}
        />
      )}
    </div>
  );
}

function MenuIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}
