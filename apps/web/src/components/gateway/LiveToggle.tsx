import { useId } from "react";

import styles from "./LiveToggle.module.css";

interface LiveToggleProps {
  on: boolean;
  onChange: (on: boolean) => void;
}

/** The Live control: the Lunaris moon, which lights amber when a session is what you will get.
 *
 *  The brand mark doubles as the switch because the moon IS the product. Off it is a quiet muted
 *  glyph; on it takes the accent and the word "Live" appears beside it, because a control whose
 *  entire state is a hue change is unreadable to anyone who cannot see that hue.
 *
 *  Presentational: whether Lunaris has two products at all is the parent's call, not this
 *  component's. */
export function LiveToggle({ on, onChange }: LiveToggleProps) {
  const maskId = `live-moon-${useId().replace(/:/g, "")}`;

  return (
    <button
      type="button"
      className={styles.toggle}
      aria-pressed={on}
      aria-label={on ? "Live mode, on" : "Live mode, off"}
      title="Teach me in a live session"
      onClick={() => onChange(!on)}
    >
      <svg
        className={styles.moon}
        width="18"
        height="18"
        viewBox="0 0 64 64"
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <mask id={maskId}>
          <rect width="64" height="64" fill="#fff" />
          <circle cx="32" cy="22" r="21" fill="#000" />
        </mask>
        <circle cx="32" cy="34" r="22" mask={`url(#${maskId})`} />
        <circle cx="32" cy="26" r="8" />
      </svg>
      {on && <span className={styles.label}>Live</span>}
    </button>
  );
}
