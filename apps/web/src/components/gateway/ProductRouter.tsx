import { lazy, Suspense, type ReactNode } from "react";
import { useLocation } from "react-router";

import { useIsProductForked } from "../../hooks/useIsProductForked";
import { resolveProductRoute } from "../../lib/routes";
import styles from "./ProductRouter.module.css";

// Live is code-split at the product boundary: Studio's bundle must never carry Live's dependencies,
// and Live is about to grow a large UI stack. Splitting now costs one lazy() and makes the boundary
// structural rather than a rule someone has to remember.
const LiveShell = lazy(() => import("../live/LiveShell"));

interface ProductRouterProps {
  /** Studio's app, rendered for every path Live does not claim. */
  studio: ReactNode;
  /** Where the API lives — Live compiles its concept graph through it. */
  apiBaseUrl: string;
}

/** Routes a URL to its product.
 *
 *  Phase 0.5 moved the fork itself into the composer — you choose Studio or Live at the moment you
 *  name a topic, not at login — so this is now pure routing: no gateway, and no remembered product.
 *  `/` unconditionally means Studio Home again.
 *
 *  Transparent when Live is flagged off or auth is unconfigured: Lunaris is then Studio alone and
 *  `/live` falls through to Studio's not-found. */
export function ProductRouter({ studio, apiBaseUrl }: ProductRouterProps) {
  const forked = useIsProductForked();
  const { pathname } = useLocation();

  if (!forked || resolveProductRoute(pathname) !== "live") return <>{studio}</>;

  return (
    <Suspense fallback={<div className={styles.loading} role="status" aria-live="polite" />}>
      <LiveShell apiBaseUrl={apiBaseUrl} />
    </Suspense>
  );
}
