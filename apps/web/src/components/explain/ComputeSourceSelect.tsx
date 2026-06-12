import { useId } from "react";

import { useComputeSource } from "../../hooks/useComputeSource";
import type { ComputeSource } from "../../lib/computeSource";
import styles from "./ComputeSourceSelect.module.css";

interface ComputeSourceSelectProps {
  /** "full" (Settings): the spelled-out trade-off hint for both choices.
   *  "compact" (the Draft banner's status row): only the load-bearing hint — the tab-open
   *  contract while "This device" is chosen, or the unsupported reason when WebGPU is
   *  missing. */
  variant?: "full" | "compact";
}

const SOURCE_LABELS: Record<ComputeSource, string> = {
  server: "Lunaris server",
  device: "This device",
};

/** The keyless user's per-device choice of where the Draft tier's AI runs — builds AND
 *  explanations: the Lunaris server (capped/slower, but the tab can close) or this device
 *  (free and unlimited over WebGPU, but a build needs its tab kept open). A two-option choice,
 *  so it renders as a segmented control (native radios underneath), not a dropdown. Rendered
 *  on the Draft banner (compact) and in Settings (full); keyed users never see it (their model
 *  is hosted). The device segment is disabled — with the reason shown — when the browser lacks
 *  WebGPU. */
export function ComputeSourceSelect({ variant = "full" }: ComputeSourceSelectProps) {
  const { source, setSource, device } = useComputeSource();
  const groupId = useId();
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

  const renderSegment = (value: ComputeSource, isDisabled = false) => (
    <label
      className={styles.segment}
      data-checked={source === value || undefined}
      data-disabled={isDisabled || undefined}
    >
      <input
        type="radio"
        name={groupId}
        value={value}
        className={styles.radio}
        checked={source === value}
        disabled={isDisabled}
        onChange={() => setSource(value)}
      />
      {SOURCE_LABELS[value]}
    </label>
  );

  return (
    <div className={styles.field}>
      <span className={`eyebrow ${styles.label}`} id={groupId}>
        Draft AI runs on
      </span>
      <div
        role="radiogroup"
        aria-labelledby={groupId}
        aria-describedby={hint ? hintId : undefined}
        className={styles.segments}
      >
        {renderSegment("server")}
        {renderSegment("device", !device.supported)}
      </div>
      {hint && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
    </div>
  );
}
