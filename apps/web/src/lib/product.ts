/** The two Lunaris products. Studio is the course factory; Live is the learner-facing session
 *  product. Chosen per topic in the composer (Phase 0.5) rather than remembered per account. */
export type Product = "studio" | "live";

/** Whether Lunaris Live is offered at all. Off by default: with the flag unset there is no Mode row
 *  in the composer and `/live` is Studio's not-found — nothing a user can observe changes. Read per
 *  call (not captured at module load) so it stays overridable in tests. */
export function isLiveEnabled(): boolean {
  return import.meta.env.VITE_LIVE_ENABLED === "true";
}
