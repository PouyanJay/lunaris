import { useEffect, useState } from "react";

import type { Theme } from "./useTheme";

/** Read the active theme straight off `<html data-theme>` (default light) — the same attribute the
 *  no-flash boot script and `useTheme` set. */
function readTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/**
 * The active theme as a READ-ONLY value that tracks live changes to `<html data-theme>`.
 *
 * Unlike {@link useTheme}, this never writes the attribute, `theme-color`, or storage — it only
 * observes. That lets any component react to the theme (e.g. a cover picking the contrasting image)
 * without owning it or racing the shell's single `useTheme` writer, and without threading a `theme`
 * prop down to every card site. A `MutationObserver` keeps it in sync when the user toggles the
 * theme; the attribute is re-read once on mount to catch a change between first render and effect.
 */
export function useThemeValue(): Theme {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setTheme(readTheme());
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return theme;
}
