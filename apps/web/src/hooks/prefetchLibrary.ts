import { getLibraryCache, setLibraryCache } from "./libraryCache";
import { fetchCourseSummaries } from "../lib/library";

// Guards a prefetch in flight, so a hover that lingers (or repeated pointer enter/leave) fires one
// request, not a burst.
let prefetching = false;

/**
 * Warm the library cache on intent — a hover / focus of the "My courses" nav item — so the click
 * lands on ready data instead of a skeleton. Best-effort and cheap: it no-ops when the grid is
 * already cached or a prefetch is in flight, and swallows errors (the real load, on navigation,
 * surfaces them and retries). Kept out of `libraryCache` so that module stays free of the
 * data-fetching layer (the test harness / AuthProvider import only the reset).
 */
export function prefetchLibrary(apiBaseUrl: string): void {
  if (getLibraryCache() !== null || prefetching) return;
  prefetching = true;
  fetchCourseSummaries(apiBaseUrl)
    .then((courses) => setLibraryCache(courses))
    .catch(() => {
      // A prefetch is a nicety — leave the cache cold so the real navigation load owns the error.
    })
    .finally(() => {
      prefetching = false;
    });
}
