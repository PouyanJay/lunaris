import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "lunaris-theme";
const THEME_COLOR = { light: "#ffffff", dark: "#090a0c" } as const;

/** The active theme at mount — mirrors what the no-flash boot script in index.html already set on
 *  <html> (default light). Reading the live attribute keeps the hook in sync with that first paint. */
function readInitialTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

interface ThemeControl {
  theme: Theme;
  /** Flip light ⇄ dark. */
  toggle: () => void;
}

/** The active theme + its toggle, threaded down to whichever shell renders the toggle button. */
export interface ThemeProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/**
 * Light/dark theme with a one-button toggle. Default is light; the choice persists in localStorage
 * and is reapplied before first paint by the boot script in index.html (so there's no flash). The
 * hook keeps the `<html data-theme>` attribute, the `theme-color` meta, and storage in sync on every
 * change. Token-driven: components never branch on the theme — they consume the CSS variables that
 * `[data-theme="dark"]` overrides.
 */
export function useTheme(): ThemeControl {
  const [theme, setTheme] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Private mode / storage disabled — the in-memory theme still applies for this session.
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
