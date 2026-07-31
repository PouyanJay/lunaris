import type { MouseEvent } from "react";
import { Link } from "react-router";

import type { Product } from "../../lib/product";
import { PRODUCT_ROUTES, ROUTES } from "../../lib/routes";
import { BrandMark } from "../shell/BrandMark";
import styles from "./ProductGateway.module.css";

interface ProductGatewayProps {
  /** Records the choice so the next sign-in skips this screen. Fired alongside the navigation the
   *  link performs — the choice is what turns a gateway into a gateway *with memory*. */
  onChoose: (product: Product) => void;
}

/** Whether a click will actually navigate *this* tab. A modified click (cmd/ctrl/shift/alt) or a
 *  non-primary button is the browser's "open elsewhere" gesture, which react-router's Link also
 *  declines to handle — so the current tab stays put and the choice must NOT be recorded. Without
 *  this, cmd-clicking Live to peek at it in a new tab would silently repoint the tab you are
 *  standing in. */
function navigatesThisTab(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

/** The first-run fork between the two Lunaris products.
 *
 *  Deliberately post-authentication: sign-in stays single and frictionless, and the OAuth callback
 *  never has to know a fork exists. Shown only when the account has no usable remembered product,
 *  so it is a first-run and fallback surface rather than a daily toll booth.
 *
 *  Both choices are real links, not buttons — they navigate, so they must be openable in a new tab
 *  and announced as links. */
export function ProductGateway({ onChoose }: ProductGatewayProps) {
  return (
    <div className={styles.screen}>
      <div className={styles.brand}>
        <BrandMark size={28} />
        <span className={styles.wordmark}>Lunaris</span>
      </div>
      <p className={styles.lede}>Two ways to work. Pick one — you can switch any time.</p>
      <section className={styles.panels} aria-label="Choose a product">
        <Link
          to={ROUTES.home}
          className={`${styles.panel} ${styles.studio}`}
          onClick={(event) => navigatesThisTab(event) && onChoose("studio")}
        >
          <span className={styles.eyebrow}>Create</span>
          <span className={styles.name}>Lunaris Studio</span>
          <span className={styles.blurb}>
            Compile a topic into a publishable course — validated curriculum, written lessons,
            narrated videos.
          </span>
        </Link>
        <Link
          to={PRODUCT_ROUTES.live}
          className={`${styles.panel} ${styles.live}`}
          onClick={(event) => navigatesThisTab(event) && onChoose("live")}
        >
          <span className={styles.eyebrow}>Learn</span>
          <span className={styles.name}>Lunaris Live</span>
          <span className={styles.blurb}>
            Sit down with a tutor that teaches in real time, watches what you do, and remembers what
            you know.
          </span>
        </Link>
      </section>
    </div>
  );
}
