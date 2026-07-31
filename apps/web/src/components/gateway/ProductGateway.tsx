import { useId, type MouseEvent } from "react";
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
 *  Composed as ONE hairline-divided instrument rather than two floating cards: the products are
 *  halves of a single choice, and the house idiom welds regions together with rules instead of
 *  scattering bordered cards on a ground.
 *
 *  Both choices are real links, not buttons — they navigate, so cmd-click, middle-click and "open
 *  in new tab" all have to work. */
export function ProductGateway({ onChoose }: ProductGatewayProps) {
  const titleId = useId();

  return (
    <main className={styles.screen}>
      <section className={styles.gateway} aria-labelledby={titleId}>
        <div className={styles.masthead}>
          <div className={styles.brand}>
            <BrandMark size={26} />
            <span className={styles.wordmark}>Lunaris</span>
          </div>
          <h1 id={titleId} className={styles.title}>
            Choose a product
          </h1>
          <p className={styles.lede}>You can switch any time — we&rsquo;ll remember this one.</p>
        </div>

        <div className={styles.panels}>
          <Link
            to={ROUTES.home}
            className={`${styles.panel} ${styles.studio}`}
            onClick={(event) => navigatesThisTab(event) && onChoose("studio")}
          >
            <span className={`eyebrow ${styles.eyebrow}`}>Create</span>
            <h2 className={styles.name}>Lunaris Studio</h2>
            <span className={styles.blurb}>
              Compile a topic into a publishable course — validated curriculum, written lessons, and
              narrated videos you can share.
            </span>
          </Link>

          <Link
            to={PRODUCT_ROUTES.live}
            className={`${styles.panel} ${styles.live}`}
            onClick={(event) => navigatesThisTab(event) && onChoose("live")}
          >
            <span className={`eyebrow ${styles.eyebrow}`}>
              {/* Live is the product that runs in real time, and this is the one live signal on the
                  screen. Not StatusDot: that primitive is a status *readout* (RUNNING / FAILED)
                  with its own typographic contract, and this is a product-identity mark sitting in
                  an eyebrow. It borrows StatusDot's halo motion so the app keeps one live-motion
                  language. Decorative — the word beside it carries the meaning. */}
              <span className={styles.pulse} aria-hidden="true" />
              Learn
            </span>
            <h2 className={styles.name}>Lunaris Live</h2>
            <span className={styles.blurb}>
              Sit down with a tutor that teaches in real time, watches what you do, and remembers
              what you know.
            </span>
          </Link>
        </div>
      </section>
    </main>
  );
}
