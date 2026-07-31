import { Badge } from "../primitives/Badge";
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
  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <BrandMark size={24} />
          <span className={styles.wordmark}>Lunaris</span>
          {/* The house Badge primitive, accent tint — states which product you are in without a
              second wordmark. T5 replaces this with the product switcher. */}
          <Badge category="accent">Live</Badge>
        </div>
      </header>
      <main className={styles.canvas}>
        <div className={styles.empty}>
          <p className={styles.eyebrow}>Coming soon</p>
          <h1 className={styles.title}>Lunaris Live</h1>
          <p className={styles.body}>
            Live teaches through sessions: a tutor that watches what you do, breaks things with you,
            and remembers what you know. The session runtime is still being built — there is nothing
            to join yet.
          </p>
        </div>
      </main>
    </div>
  );
}
