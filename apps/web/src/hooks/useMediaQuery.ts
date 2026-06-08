import { useEffect, useState } from "react";

/** Reactively track a CSS media query. Returns false until mounted (and in jsdom / environments
 *  without `matchMedia`), so server/test renders get the desktop layout and the client corrects on
 *  mount. Used to switch the shell to its mobile drawer layout below the phone breakpoint. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** The phone breakpoint (see index.css): below this the shell uses drawers + full-width content. */
export const MOBILE_QUERY = "(max-width: 768px)";
