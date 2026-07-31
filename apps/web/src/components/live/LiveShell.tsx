import { useEffect } from "react";
import { Link } from "react-router";

import { ROUTES } from "../../lib/routes";
import { BrandMark } from "../shell/BrandMark";
import styles from "./LiveShell.module.css";

/** Lunaris Live's app shell.
 *
 *  Phase 0 ships the shell and nothing behind it: the product route-space has to exist before the
 *  gateway has a second destination to fork to. The canvas is a designed empty state rather than a
 *  spinner or a blank — Live genuinely has no sessions yet, and saying so is the honest surface.
 *  Phase 1 fills this with the concept graph; Phase 2 with the session loop.
 *
 *  Loaded lazily by {@link ProductRouter} so Live's future dependencies never reach Studio's
 *  bundle. */
export default function LiveShell() {
  // Both products are served from one index.html, whose static <title> names Studio. Live must not
  // wear it — an accurate title per surface is the contract, and the browser tab is the one place
  // the wrong product name is visible at a glance.
  useEffect(() => {
    const previous = document.title;
    document.title = "Lunaris Live";
    return () => {
      document.title = previous;
    };
  }, []);

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <BrandMark size={24} />
          <span className={styles.wordmark}>Lunaris</span>
        </div>
      </header>
      <main className={styles.canvas}>
        <div className={styles.empty}>
          <p className={`eyebrow ${styles.eyebrow}`}>Coming soon</p>
          <h1 className={styles.title}>Lunaris Live</h1>
          <p className={styles.body}>
            Live teaches through sessions: a tutor that watches what you do, breaks things with you,
            and remembers what you know. The session runtime is still being built — there is nothing
            to join yet.
          </p>
          {/* No dead ends: an empty state has to offer somewhere to go, and until Live has
              sessions the only honest next step is the product that does. */}
          <Link to={ROUTES.home} className={styles.action}>
            Go to Lunaris Studio
          </Link>
        </div>
      </main>
    </div>
  );
}
