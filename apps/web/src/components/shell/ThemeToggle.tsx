import type { Theme } from "../../hooks/useTheme";
import { MoonIcon, SunIcon } from "./themeIcons";
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
