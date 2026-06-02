import type { Theme } from "../../hooks/useTheme";
import styles from "./ThemeToggle.module.css";

interface ThemeToggleProps {
  theme: Theme;
  onToggle: () => void;
  className?: string | undefined;
}

/** One icon button that flips light ⇄ dark. Shows the icon of the theme it will switch TO (a moon in
 *  light mode → go dark; a sun in dark mode → go light), with the action in its accessible name. */
export function ThemeToggle({ theme, onToggle, className }: ThemeToggleProps) {
  const goingDark = theme === "light";
  const label = `Switch to ${goingDark ? "dark" : "light"} mode`;
  return (
    <button
      type="button"
      className={`${styles.toggle} ${className ?? ""}`.trim()}
      onClick={onToggle}
      aria-label={label}
      aria-pressed={theme === "dark"}
      title={label}
    >
      {goingDark ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M12 2v2.5M12 19.5V22M4.22 4.22l1.77 1.77M18.01 18.01l1.77 1.77M2 12h2.5M19.5 12H22M4.22 19.78l1.77-1.77M18.01 5.99l1.77-1.77"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
