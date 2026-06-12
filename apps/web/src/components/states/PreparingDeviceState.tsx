import type { DeviceProgress } from "../../lib/deviceEngine";
import { ProgressBar } from "../primitives/ProgressBar";
import styles from "./DataStates.module.css";

interface PreparingDeviceStateProps {
  topic: string;
  /** Null until WebLLM reports its first beat (the brief moment before the fetch starts). */
  progress: DeviceProgress | null;
}

/** Shown while a device-compute build downloads + boots the on-device model, BEFORE the build
 *  starts. The download is front-loaded so the server never waits it out mid-run; the first
 *  download is ~1.8 GB (cached by the browser afterwards), so it gets a real, determinate bar.
 *  This is also where the tab-open contract starts: the coming build runs on this device. */
export function PreparingDeviceState({ topic, progress }: PreparingDeviceStateProps) {
  return (
    <div className={styles.center}>
      <div className={styles.message}>
        {/* Only the static framing is a live region — WebLLM's per-beat progress text would
            otherwise be announced on every download tick. The bar stays queryable via its
            progressbar role without being chatty. */}
        <div role="status">
          <span className="eyebrow">Preparing your device</span>
          <h2 className={styles.title}>Loading the on-device model</h2>
          <p className={styles.body}>
            “{topic}” will build using this device — the model loads first (about 1.8{" "}GB
            the first time, then cached). Keep this tab open: the build runs only while it stays
            open.
          </p>
        </div>
        <ProgressBar value={progress?.progress ?? 0} label="Model download" />
        {progress && <p className={styles.body}>{progress.text}</p>}
      </div>
    </div>
  );
}
