import { forwardRef } from "react";

import styles from "./SidebarToggle.module.css";

interface SidebarToggleProps {
  /** Whether the sidebar is currently collapsed — drives the label (the icon is the same glyph). */
  collapsed: boolean;
  onClick: () => void;
}

/** Icon-only control that collapses / expands the sidebar (the panel-rail glyph). Lives in the
 *  sidebar header when expanded and in the canvas header when collapsed, so there's always an
 *  affordance to get the rail back. Labelled per direction for screen readers. Ref-forwarding so
 *  focus can move to the expand control when the rail collapses out from under it. */
export const SidebarToggle = forwardRef<HTMLButtonElement, SidebarToggleProps>(
  function SidebarToggle({ collapsed, onClick }, ref) {
    const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
    return (
      <button
        ref={ref}
        type="button"
        className={styles.toggle}
        onClick={onClick}
        aria-label={label}
        aria-expanded={!collapsed}
        title={label}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <rect
            x="1.75"
            y="2.75"
            width="12.5"
            height="10.5"
            rx="2"
            stroke="currentColor"
            strokeWidth="1.3"
          />
          <line x1="6" y1="2.75" x2="6" y2="13.25" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      </button>
    );
  },
);
