import { useId } from "react";

import { useComputeSource } from "../../hooks/useComputeSource";
import type { ComputeSource } from "../../lib/computeSource";
import styles from "./ComputeSourceSelect.module.css";

/** The keyless user's per-device choice of where the Draft tier's AI runs — builds AND
 *  explanations: the Lunaris server (capped/slower, but the tab can close) or this device
 *  (free and unlimited over WebGPU, but a build needs its tab kept open). The trade is spelled
 *  out in the hint — never implied. Rendered on the Draft banner and in Settings; keyed users
 *  never see it (their model is hosted). The device option is disabled — with the reason
 *  shown — when the browser lacks WebGPU. */
export function ComputeSourceSelect() {
  const { source, setSource, device } = useComputeSource();
  const selectId = useId();
  const hintId = useId();

  return (
    <div className={styles.field}>
      <label className={`eyebrow ${styles.label}`} htmlFor={selectId}>
        Draft AI runs on
      </label>
      <select
        id={selectId}
        className={styles.select}
        value={source}
        onChange={(event) => setSource(event.target.value as ComputeSource)}
        aria-describedby={hintId}
      >
        <option value="server">Lunaris server</option>
        <option value="device" disabled={!device.supported}>
          This device
        </option>
      </select>
      <p className={styles.hint} id={hintId}>
        {!device.supported
          ? device.reason
          : source === "device"
            ? "Free and unlimited, in your browser (one-time ~1.8 GB model download). " +
              "Builds run only while you keep this tab open — closing it ends the build."
            : "Builds run on the shared free server and explanations have a small daily " +
              "allowance, but you can close this tab and walk away mid-build."}
      </p>
    </div>
  );
}
