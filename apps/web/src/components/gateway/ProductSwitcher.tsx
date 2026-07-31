import { Link } from "react-router";

import { useProductFork } from "../../hooks/useProductFork";
import type { Product } from "../../lib/product";
import { PRODUCT_ROUTES, ROUTES } from "../../lib/routes";
import styles from "./ProductSwitcher.module.css";

interface ProductSwitcherProps {
  /** The product whose shell is rendering this. Marked with `aria-current`. */
  current: Product;
}

const DESTINATIONS: { product: Product; label: string; to: string }[] = [
  { product: "studio", label: "Lunaris Studio", to: ROUTES.home },
  { product: "live", label: "Lunaris Live", to: PRODUCT_ROUTES.live },
];

/** Crossing between the two products, docked in both top bars.
 *
 *  Real links in a real `<nav>`, not a segmented radio control: these navigate, so cmd-click and
 *  "open in new tab" have to work, and the current product is announced via `aria-current` rather
 *  than conveyed by colour alone.
 *
 *  Renders nothing at all when Lunaris is a single product, so Studio's chrome is untouched until
 *  Live is switched on. */
export function ProductSwitcher({ current }: ProductSwitcherProps) {
  const forked = useProductFork();
  if (!forked) return null;

  return (
    <nav className={styles.switcher} aria-label="Product">
      {DESTINATIONS.map(({ product, label, to }) => (
        <Link
          key={product}
          to={to}
          className={styles.option}
          data-current={product === current ? "" : undefined}
          {...(product === current ? { "aria-current": "page" as const } : {})}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
