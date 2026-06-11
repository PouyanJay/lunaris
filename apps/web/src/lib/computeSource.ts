/** Where a keyless user's explanations are generated. "server" is the keyless Lunaris endpoint
 *  (capped per day); "device" runs the model in this browser over WebGPU. Keyed users always get
 *  the hosted model and never see this choice. */
export type ComputeSource = "server" | "device";

/** The localStorage key. The choice is intentionally per-DEVICE, not per-account: WebGPU support
 *  and the cached model weights live in this browser, so a laptop can say "device" while the same
 *  account's phone stays on "server". */
export const COMPUTE_SOURCE_KEY = "lunaris.explainComputeSource";

const DEFAULT_SOURCE: ComputeSource = "server";

/** The device's saved compute choice, defaulting to the server (today's behavior — on-device is
 *  always an explicit opt-in). A corrupted or legacy value falls back to the default. */
export function loadComputeSource(): ComputeSource {
  try {
    const stored = localStorage.getItem(COMPUTE_SOURCE_KEY);
    return stored === "device" || stored === "server" ? stored : DEFAULT_SOURCE;
  } catch {
    return DEFAULT_SOURCE; // storage unavailable (private mode/embedded) → today's behavior
  }
}

export function saveComputeSource(source: ComputeSource): void {
  try {
    localStorage.setItem(COMPUTE_SOURCE_KEY, source);
  } catch {
    // Storage unavailable — the choice simply doesn't persist past this page.
  }
}

export interface WebGpuSupport {
  supported: boolean;
  /** Why "This device" is unavailable, shown verbatim next to the disabled option. */
  reason: string | null;
}

/** Whether this browser can run the on-device model. A synchronous presence check is the dropdown's
 *  gate; the engine performs the real adapter probe when it boots (T3). */
export function detectWebGpu(): WebGpuSupport {
  if (typeof navigator !== "undefined" && "gpu" in navigator) {
    return { supported: true, reason: null };
  }
  return {
    supported: false,
    reason: "This browser doesn't support WebGPU — explanations will use the Lunaris server.",
  };
}
