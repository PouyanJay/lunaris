import { useCallback, useMemo, useState } from "react";

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

/** The device's explain compute choice as React state, persisted on every change. Detection runs
 *  once per mount — WebGPU support can't change within a page's lifetime. */
export function useComputeSource(): UseComputeSource {
  const device = useMemo(detectWebGpu, []);
  const [source, setSourceState] = useState<ComputeSource>(loadComputeSource);

  const setSource = useCallback((next: ComputeSource) => {
    saveComputeSource(next);
    setSourceState(next);
  }, []);

  return { source, setSource, device };
}
