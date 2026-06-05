import { useId, useState, type ReactNode } from "react";

import styles from "./CollapsibleSection.module.css";

interface CollapsibleSectionProps {
  /** Small uppercase micro-label above the title (the house eyebrow). */
  eyebrow: string;
  /** The section title — also the disclosure's accessible name. */
  title: string;
  /** Whether the body starts expanded. Defaults to open. */
  defaultOpen?: boolean;
  /** An optional control rendered beside the header, outside the disclosure trigger (e.g. "Done"). */
  action?: ReactNode;
  children: ReactNode;
}

/** A panel whose body collapses behind its header — the WAI-ARIA accordion/disclosure pattern: a
 *  heading-wrapped toggle button (`aria-expanded` + `aria-controls`) over a labelled region. One
 *  reusable chrome for the settings sections so each reads as a dropdown, not an endless scroll. */
export function CollapsibleSection({
  eyebrow,
  title,
  defaultOpen = true,
  action,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const baseId = useId();
  const triggerId = `${baseId}-trigger`;
  const bodyId = `${baseId}-body`;

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.headingWrap}>
          <button
            type="button"
            id={triggerId}
            className={styles.trigger}
            aria-expanded={open}
            aria-controls={bodyId}
            onClick={() => setOpen((value) => !value)}
          >
            <span className={styles.heading}>
              <span className="eyebrow">{eyebrow}</span>
              <span className={styles.title}>{title}</span>
            </span>
            <span className={styles.chevron} data-open={open} aria-hidden="true" />
          </button>
        </h2>
        {action && <div className={styles.action}>{action}</div>}
      </div>
      <div
        id={bodyId}
        role="region"
        aria-labelledby={triggerId}
        className={styles.body}
        hidden={!open}
      >
        {children}
      </div>
    </section>
  );
}
