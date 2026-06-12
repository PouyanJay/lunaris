import { AccentBand } from "./primitives/AccentBand";
import styles from "./DeviceBuildNotice.module.css";

/** The in-build half of the tab-open contract: shown for the whole life of a device-compute
 *  build, because the consequence (closing the tab kills the build) holds for its whole life —
 *  the dropdown hint and the preparing screen only cover the moments before it. */
export function DeviceBuildNotice() {
  return (
    <AccentBand className={styles.row}>
      <span className={`eyebrow ${styles.eyebrow}`}>On-device build</span>
      <p className={styles.text}>
        This build is running on your device — keep this tab open and your device awake until it
        finishes. Closing the tab ends the build.
      </p>
    </AccentBand>
  );
}
