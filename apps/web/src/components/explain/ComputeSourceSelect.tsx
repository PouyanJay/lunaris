import { useId } from "react";

import { useComputeSource } from "../../hooks/useComputeSource";
import type { ComputeSource } from "../../lib/computeSource";
import styles from "./ComputeSourceSelect.module.css";

/** The keyless user's per-device choice of where explanations run: the Lunaris server (capped,
 *  works everywhere) or this device (WebGPU, one-time model download). Rendered on the Draft
 *  banner and in Settings; keyed users never see it (their explains are hosted). The device
 *  option is disabled — with the reason shown — when the browser lacks WebGPU. */
export function ComputeSourceSelect() {
  const { source, setSource, device } = useComputeSource();
  const selectId = useId();
  const hintId = useId();

  return (
    <div className={styles.field}>
      <label className={`eyebrow ${styles.label}`} htmlFor={selectId}>
        Explanations run on
      </label>
      <select
        id={selectId}
        className={styles.select}
        value={source}
        onChange={(event) => setSource(event.target.value as ComputeSource)}
        aria-describedby={device.supported ? undefined : hintId}
      >
        <option value="server">Lunaris server</option>
        <option value="device" disabled={!device.supported}>
          This device
        </option>
      </select>
      {device.supported ? (
        <p className={styles.hint}>
          {source === "device"
            ? "Runs in your browser after a one-time model download (~1.8 GB)."
            : "A small daily allowance; switch to this device for unlimited explanations."}
        </p>
      ) : (
        <p className={styles.hint} id={hintId}>
          {device.reason}
        </p>
      )}
    </div>
  );
}
