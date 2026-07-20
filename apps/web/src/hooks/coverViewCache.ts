import type { CoverJobView } from "../lib/coverJobs";

// The last resolved cover view per job, held at module scope so it survives navigation: the
// Overview (and any surface that must exchange a jobId for signed URLs) renders its cover instantly
// on a revisit — the service worker serves the bytes — while the exchange revalidates in the
// background. Entries expire before the signed URLs inside them do (1h), so a cache hit never
// serves a URL that is already dead on arrival. Type-only import keeps this module dependency-free
// (the test harness and AuthProvider import only the reset).

/** How long a resolved view stays servable — safely under the signed URLs' 1-hour TTL. */
const COVER_VIEW_TTL_MS = 45 * 60 * 1000;

interface CachedView {
  view: CoverJobView;
  storedAt: number;
}

const viewsByJob = new Map<string, CachedView>();

/** The cached view for a cover job, or null when absent/expired (a cold exchange is needed). */
export function getCoverView(jobId: string): CoverJobView | null {
  const entry = viewsByJob.get(jobId);
  if (!entry) return null;
  if (Date.now() - entry.storedAt > COVER_VIEW_TTL_MS) {
    viewsByJob.delete(jobId);
    return null;
  }
  return entry.view;
}

/** Record a freshly-exchanged view so the next mount renders it without waiting on the API. */
export function setCoverView(jobId: string, view: CoverJobView): void {
  viewsByJob.set(jobId, { view, storedAt: Date.now() });
}

/** Drop every cached view. Called on an account switch (jobIds are per-user anyway — this is
 *  hygiene, not a security boundary) and by the test harness between tests. */
export function clearCoverViews(): void {
  viewsByJob.clear();
}
