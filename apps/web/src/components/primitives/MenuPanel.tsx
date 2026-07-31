import { useRef, useState, type ReactNode } from "react";

import styles from "./Menu.module.css";
import { useDismissable } from "./useDismissable";

interface MenuPanelProps {
  /** The setting's name, shown as the chip's key. */
  label: string;
  /** The chip's current reading. Carries the state, so the bar says whether this is set without
   *  being opened. */
  value: string;
  /** Marks the chip as carrying a chosen value rather than an invitation. */
  set?: boolean;
  /** Rendered inside the panel. Receives a close callback for its own dismiss action. */
  children: (close: () => void) => ReactNode;
  /** Hangs the panel from the chip's right edge. For a wide panel on a chip that sits well along
   *  the bar, left-anchoring would push it off the viewport. */
  align?: "left" | "right";
}

/** A chip that opens a panel of arbitrary content, in the same language as {@link Menu}.
 *
 *  Menu is for choosing one of a list; this is for everything else that belongs in the composer's
 *  dock. Escape closes and returns focus to the chip, because losing focus to the body is what
 *  strands a keyboard user. */
export function MenuPanel({ label, value, set = false, children, align = "left" }: MenuPanelProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useDismissable(open, () => setOpen(false), triggerRef, panelRef);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  return (
    <div className={styles.wrap}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.chip}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : setOpen(true))}
      >
        {set && <span className={styles.key}>{label}</span>}
        <span className={styles.value}>{value}</span>
        <svg
          className={styles.caret}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          ref={panelRef}
          className={`${styles.panel} ${align === "right" ? styles.panelRight : ""}`}
          role="dialog"
          aria-label={label}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            close();
          }}
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}
