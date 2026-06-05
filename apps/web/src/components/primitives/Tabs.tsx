import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import styles from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: ReactNode;
}

interface TabsProps {
  /** The tabs, in display order. */
  tabs: TabItem[];
  /** The currently selected tab id (controlled). */
  activeId: string;
  onChange: (id: string) => void;
  /** Accessible name for the tablist. */
  label: string;
  /** Extra class on the panel — e.g. to confine + scroll a long list. */
  panelClassName?: string | undefined;
  /** The active tab's panel content. */
  children: ReactNode;
}

/** A controlled, accessible tab set (WAI-ARIA tabs pattern): a `role="tablist"` of roving-tabindex
 *  tabs over one `role="tabpanel"` whose content the parent swaps per `activeId`. Arrow keys + Home/
 *  End move between tabs; the panel is focusable so a confined, scrollable list stays keyboard-reachable. */
export function Tabs({ tabs, activeId, onChange, label, panelClassName, children }: TabsProps) {
  const baseId = useId();
  const panelId = `${baseId}-panel`;
  const tabId = (id: string) => `${baseId}-tab-${id}`;
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = tabs.findIndex((t) => t.id === activeId);
    if (index < 0) return;
    let next = -1;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    const nextTab = next < 0 ? undefined : tabs[next];
    if (!nextTab) return;
    event.preventDefault();
    onChange(nextTab.id);
    tabRefs.current[nextTab.id]?.focus();
  }

  return (
    <div className={styles.tabs}>
      <div role="tablist" aria-label={label} className={styles.tablist}>
        {tabs.map((tab) => {
          const active = tab.id === activeId;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={tabId(tab.id)}
              ref={(node) => {
                tabRefs.current[tab.id] = node;
              }}
              className={styles.tab}
              data-active={active}
              aria-selected={active}
              aria-controls={panelId}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={onKeyDown}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId(activeId)}
        tabIndex={0}
        className={panelClassName ? `${styles.panel} ${panelClassName}` : styles.panel}
      >
        {children}
      </div>
    </div>
  );
}
