import { useCallback, useEffect, useState } from "react";

/** The theme actually applied to the document (what `[data-theme]` is set to). */
export type Theme = "light" | "dark";

/** What the user chose. `system` follows the OS `prefers-color-scheme` live; `light`/`dark` pin it. */
export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "lunaris-theme";
const THEME_COLOR = { light: "#ffffff", dark: "#090a0c" } as const;
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isPreference(value: string | null): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}

/** The stored preference, or — when none is stored — whatever the boot script already painted on
 *  `<html>` (so the hook mirrors the first paint), defaulting to `light`. */
function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isPreference(stored)) return stored;
  } catch {
    // Private mode / storage disabled — fall through to the painted attribute.
  }
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** The OS preference right now (dark?), false when `matchMedia` is unavailable. */
function systemPrefersDark(): boolean {
  return typeof matchMedia === "function" && matchMedia(DARK_QUERY).matches;
}

/** Resolve a preference to the concrete theme to apply. */
function resolveTheme(preference: ThemePreference): Theme {
  if (preference === "system") return systemPrefersDark() ? "dark" : "light";
  return preference;
}

interface ThemeControl {
  /** The resolved theme applied to the document (`light`/`dark`). */
  theme: Theme;
  /** The user's choice (`light`/`dark`/`system`) — what the Appearance control reflects. */
  preference: ThemePreference;
  /** Pick a preference (Appearance section). */
  setPreference: (preference: ThemePreference) => void;
  /** Quick flip light ⇄ dark (the sidebar toggle) — always lands on an explicit preference. */
  toggle: () => void;
}

/** The minimal theme surface the shells need for the quick-toggle. The 3-way preference control
 *  (Appearance) is threaded separately, only to the settings surface, so shells stay simple. */
export interface ThemeProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/**
 * Theme with three preferences — light, dark, or system (follows the OS `prefers-color-scheme`
 * live). Default is light; the choice persists in localStorage and is reapplied before first paint
 * by the boot script in index.html (so there's no flash). The hook keeps the resolved
 * `<html data-theme>`, the `theme-color` meta, and storage in sync on every change, and — while the
 * preference is `system` — re-resolves when the OS preference flips. Token-driven: components never
 * branch on the theme; they consume the CSS variables that `[data-theme="dark"]` overrides.
 */
export function useTheme(): ThemeControl {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(readPreference()));

  // Persist the preference and re-resolve the applied theme whenever the choice changes.
  useEffect(() => {
    setTheme(resolveTheme(preference));
    try {
      localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // Private mode / storage disabled — the in-memory preference still applies this session.
    }
  }, [preference]);

  // While on `system`, track OS changes live so a daytime→night switch flips the app with no reload.
  useEffect(() => {
    if (preference !== "system" || typeof matchMedia !== "function") return;
    const media = matchMedia(DARK_QUERY);
    const onChange = () => setTheme(media.matches ? "dark" : "light");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  // Apply the resolved theme to the document.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
  }, [theme]);

  const setPreference = useCallback((next: ThemePreference) => setPreferenceState(next), []);

  // The quick toggle flips the RESOLVED theme and pins that as an explicit preference — so from
  // `system` it lands on the opposite of whatever the OS currently shows.
  const toggle = useCallback(() => {
    setPreferenceState(resolveTheme(readPreference()) === "dark" ? "light" : "dark");
  }, []);

  return { theme, preference, setPreference, toggle };
}
