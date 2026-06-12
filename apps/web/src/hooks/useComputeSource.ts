import { useCallback, useState, useSyncExternalStore } from "react";

import {
  detectWebGpu,
  loadComputeSource,
  saveComputeSource,
  type ComputeSource,
  type WebGpuSupport,
} from "../lib/computeSource";

interface UseComputeSource {
  source: ComputeSource;
  /** Persist + apply a new choice (per device — see lib/computeSource). */
  setSource: (source: ComputeSource) => void;
  device: WebGpuSupport;
}

// The choice is read by SEVERAL mounted components at once (the segmented control, the Draft
// banner's language-model cell, Settings) — so it lives in one external store that every
// subscriber re-renders from. Per-instance useState desynced them in the field: switching the
// segment to "Lunaris server" left the banner's own copy on "device", so the model cell kept
// presenting the WebGPU engine while the control showed the server chosen.
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another TAB changing the per-device choice lands here too (the `storage` event only fires
  // for OTHER documents — same-document changes go through emit()).
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** The device's explain/build compute choice as shared React state, persisted on every change.
 *  WebGPU detection runs once per mount — support can't change within a page's lifetime. */
export function useComputeSource(): UseComputeSource {
  const [device] = useState<WebGpuSupport>(detectWebGpu);
  // getSnapshot reads straight from localStorage: a string primitive, so the snapshot is stable
  // between changes and never tears across subscribers.
  const source = useSyncExternalStore(subscribe, loadComputeSource, loadComputeSource);

  const setSource = useCallback((next: ComputeSource) => {
    saveComputeSource(next);
    emit();
  }, []);

  return { source, setSource, device };
}
