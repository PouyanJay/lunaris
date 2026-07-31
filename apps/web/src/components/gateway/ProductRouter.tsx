import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "../../hooks/useAuth";
import { useProductChoice } from "../../hooks/useProductChoice";
import { isLiveEnabled } from "../../lib/product";
import { PRODUCT_ROUTES, productEnteredAt, resolveProductRoute, ROUTES } from "../../lib/routes";
import { ProductGateway } from "./ProductGateway";
import styles from "./ProductRouter.module.css";

// Live is code-split at the product boundary: Studio's bundle must never carry Live's dependencies,
// and Live is about to grow a large UI stack. Splitting now costs one lazy() and makes the boundary
// structural rather than a rule someone has to remember.
const LiveShell = lazy(() => import("../live/LiveShell"));

interface ProductRouterProps {
  /** Studio's app, rendered for every path Live and the gateway do not claim. */
  studio: ReactNode;
}

/** Routes a signed-in user to a product, and forks first-timers to the gateway.
 *
 *  Sits between AuthGate and Studio so the fork is strictly post-authentication. Transparent when
 *  Live is flagged off or auth is unconfigured: Lunaris is then Studio alone, `/` is Home, and
 *  `/live` falls through to Studio's not-found — nothing observable changes. That is also why the
 *  existing routing suite, which runs without Supabase, keeps its current meaning. */
export function ProductRouter({ studio }: ProductRouterProps) {
  const { enabled, user, updateLastProduct } = useAuth();
  const { pathname } = useLocation();
  const { product, choose } = useProductChoice(user, enabled ? updateLastProduct : undefined);

  const active = isLiveEnabled() && enabled;
  const entered = productEnteredAt(pathname);

  // Being in a product is what makes it the remembered one, however you got there — gateway click,
  // deep link, or the switcher. Idempotent: once the preference matches, this stops firing.
  useEffect(() => {
    if (active && entered !== null && entered !== product) choose(entered);
  }, [active, entered, product, choose]);

  if (!active) return <>{studio}</>;

  const route = resolveProductRoute(pathname);
  if (route.kind === "live") {
    return (
      <Suspense fallback={<div className={styles.loading} role="status" aria-live="polite" />}>
        <LiveShell />
      </Suspense>
    );
  }
  if (route.kind === "gateway") return <ProductGateway onChoose={choose} />;

  // Only the bare root is eligible for the remembered-product redirect. Every deeper path is a deep
  // link and is left exactly where it points, so "a deep link never shows the gateway" holds by
  // construction rather than by a branch that could rot.
  if (pathname === ROUTES.home) {
    if (product === null) return <Navigate to={PRODUCT_ROUTES.gateway} replace />;
    if (product === "live") return <Navigate to={PRODUCT_ROUTES.live} replace />;
  }
  return <>{studio}</>;
}
