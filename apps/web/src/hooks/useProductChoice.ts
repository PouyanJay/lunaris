import { useCallback, useEffect, useState } from "react";

import type { User } from "@supabase/supabase-js";

import { resolveLastProduct, type Product } from "../lib/product";

/** The account's current product, and the act of choosing one.
 *
 *  The chosen product is held in local state and only *mirrored* to Supabase `user_metadata`.
 *  That ordering is deliberate: persisting goes through `updateUser` → `USER_UPDATED` → a session
 *  refresh, and if the redirect decision waited on that round trip, choosing a product would bounce
 *  the user back to the gateway for as long as it took — a visible flash at best, a loop at worst.
 *  Choosing is therefore immediate and the write is best-effort; if it fails, the only consequence
 *  is that the gateway asks again next time, which is the safe direction to fail in.
 *
 *  `persist` is optional so the hook stays usable wherever auth isn't configured. */
export function useProductChoice(
  user: User | null,
  persist?: (product: Product) => Promise<void>,
): { product: Product | null; choose: (product: Product) => void } {
  const stored = resolveLastProduct(user);
  const [product, setProduct] = useState<Product | null>(stored);

  // Adopt the stored value whenever the account's own preference changes underneath us — a session
  // refresh, or a sign-out/sign-in into a different account (whose product must not be inherited).
  useEffect(() => setProduct(stored), [stored]);

  const choose = useCallback(
    (next: Product) => {
      setProduct(next);
      // Best-effort mirror. A rejected write must not surface as an unhandled rejection or break
      // the navigation that is already underway. Wrapped in Promise.resolve so this holds however
      // the persist implementation returns — the failure mode here is a silent no-op, by design.
      void Promise.resolve(persist?.(next)).catch(() => {});
    },
    [persist],
  );

  return { product, choose };
}
