import type { CourseSummary } from "../types/course";

// The last successfully-loaded library, held at module scope so it survives navigation: My-courses
// and Home both read it, so re-entering the grid paints the last cards instantly and revalidates
// quietly instead of flashing the skeleton each time. Kept here — with only a type-only import — so
// resetting it (e.g. the test harness, the AuthProvider) never drags in the data-fetching layer.
let cached: CourseSummary[] | null = null;

/** The cached library grid, or null on a cold session (before the first successful load). */
export function getLibraryCache(): CourseSummary[] | null {
  return cached;
}

/** Record the freshly-loaded library so the next mount paints it without a skeleton. */
export function setLibraryCache(courses: CourseSummary[]): void {
  cached = courses;
}

/** Drop the cached library. Called when the signed-in user changes, so a sign-out / account switch
 *  never flashes the previous account's courses before the new library loads. */
export function clearLibraryCache(): void {
  cached = null;
}
