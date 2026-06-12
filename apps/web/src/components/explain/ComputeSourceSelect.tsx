import { useId } from "react";

import { useComputeSource } from "../../hooks/useComputeSource";
import type { ComputeSource } from "../../lib/computeSource";
import styles from "./ComputeSourceSelect.module.css";

interface ComputeSourceSelectProps {
  /** "full" (Settings): stacked label + select + the spelled-out trade-off hint.
   *  "compact" (the Draft banner's status row): inline label + select, with only the
   *  load-bearing hint — the tab-open contract while "This device" is chosen, or the
   *  unsupported reason when WebGPU is missing. */
  variant?: "full" | "compact";
}

/** The keyless user's per-device choice of where the Draft tier's AI runs — builds AND
 *  explanations: the Lunaris server (capped/slower, but the tab can close) or this device
 *  (free and unlimited over WebGPU, but a build needs its tab kept open). Rendered on the
 *  Draft banner (compact) and in Settings (full); keyed users never see it (their model is
 *  hosted). The device option is disabled — with the reason shown — when the browser lacks
 *  WebGPU. */
export function ComputeSourceSelect({ variant = "full" }: ComputeSourceSelectProps) {
  const { source, setSource, device } = useComputeSource();
  const selectId = useId();
  const hintId = useId();
  const compact = variant === "compact";

  // Compact keeps only the hint that changes what the user must DO: keep the tab open during a
  // device build, or why the device option is unavailable. The full Settings copy spells out the
  // whole trade for both choices.
  const hint = !device.supported
    ? device.reason
    : source === "device"
      ? compact
        ? "Keep this tab open during builds — closing it ends the build."
        : "Free and unlimited, in your browser (one-time ~1.8 GB model download). " +
          "Builds run only while you keep this tab open — closing it ends the build."
      : compact
        ? null
        : "Builds run on the shared free server and explanations have a small daily " +
          "allowance, but you can close this tab and walk away mid-build.";

  return (
    <div className={compact ? styles.fieldCompact : styles.field}>
      <label className={`eyebrow ${styles.label}`} htmlFor={selectId}>
        Draft AI runs on
      </label>
      <select
        id={selectId}
        className={styles.select}
        value={source}
        onChange={(event) => setSource(event.target.value as ComputeSource)}
        aria-describedby={hint ? hintId : undefined}
      >
        <option value="server">Lunaris server</option>
        <option value="device" disabled={!device.supported}>
          This device
        </option>
      </select>
      {hint && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
    </div>
  );
}
