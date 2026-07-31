import type { User } from "@supabase/supabase-js";

/** The two Lunaris products. Studio is the course factory (everything that exists today); Live is
 *  the learner-facing session product. Persisted per account so a returning user skips the
 *  gateway — see {@link resolveLastProduct}. */
export type Product = "studio" | "live";

/** The key under which the remembered product rides in Supabase `user_metadata`, alongside
 *  `display_name`. A UI preference, deliberately NOT in `user_runtime_config` — that table is
 *  per-build config mapped to environment variables. */
export const LAST_PRODUCT_KEY = "last_product";

const PRODUCTS: readonly string[] = ["studio", "live"] satisfies readonly Product[];

/** Whether Lunaris Live is offered at all. Off by default: with the flag unset there is no
 *  gateway, `/live` is Studio's not-found, and `/` is Home — nothing a user can observe changes.
 *  Read per call (not captured at module load) so it stays overridable in tests. */
export function isLiveEnabled(): boolean {
  return import.meta.env.VITE_LIVE_ENABLED === "true";
}

/** The product this account last used, or `null` when there is no usable preference.
 *
 *  Fails OPEN by design: missing, malformed, wrongly-typed, or unrecognised values all resolve to
 *  `null`, which lands the user on the gateway — a real choice — rather than a blank screen or a
 *  redirect loop. Modelled on `resolveDisplayName`, which reads `user_metadata` the same way. */
export function resolveLastProduct(user: User | null): Product | null {
  const raw = user?.user_metadata?.[LAST_PRODUCT_KEY];
  return typeof raw === "string" && PRODUCTS.includes(raw) ? (raw as Product) : null;
}
