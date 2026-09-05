import type { ReactNode } from "react";
import { NavLink } from "react-router";

import styles from "./Sidebar.module.css";

/** One primary-nav destination: a real link (NavLink sets aria-current="page" when active), the
 *  house 2px accent spine marking the active entry. Collapsed = icon-only with a tooltip name. */
export function RailNavItem({
  to,
  end,
  icon,
  label,
  collapsed,
  onNavigate,
  onPrefetch,
}: {
  to: string;
  end?: boolean;
  icon: ReactNode;
  label: string;
  collapsed: boolean;
  onNavigate?: (() => void) | undefined;
  /** Warm the destination's data on hover/focus (pointer + keyboard), so the click lands ready. */
  onPrefetch?: (() => void) | undefined;
}) {
  // Prefetch on intent from either input — a pointer hover or keyboard focus reaching the entry.
  const prefetch = onPrefetch ? { onMouseEnter: onPrefetch, onFocus: onPrefetch } : undefined;
  if (collapsed) {
    return (
      <NavLink
        to={to}
        end={end ?? false}
        onClick={onNavigate}
        {...prefetch}
        className={({ isActive }) =>
          `${styles.railAction} ${isActive ? styles.railActionActive : ""}`.trim()
        }
        aria-label={label}
        title={label}
      >
        {icon}
      </NavLink>
    );
  }
  return (
    <NavLink
      to={to}
      end={end ?? false}
      onClick={onNavigate}
      {...prefetch}
      className={({ isActive }) =>
        `${styles.navItem} ${isActive ? styles.navItemActive : ""}`.trim()
      }
    >
      <span className={styles.navIcon} aria-hidden="true">
        {icon}
      </span>
      {label}
    </NavLink>
  );
}
