import { createContext, useContext, useMemo, type ReactNode } from "react";

import { isDeviceComputeActive } from "../../lib/computeSource";
import { getDeviceEngine, type DeviceEngine, type DeviceProgress } from "../../lib/deviceEngine";
import { explainBlob } from "../../lib/explain";

/** Every tier that can answer an explain: the two server tiers (from the wire) + this browser. */
export type ExplainAnswerSource = "hosted" | "server-fallback" | "on-device";

export interface ExplainOutcome {
  explanation: string;
  source: ExplainAnswerSource;
}

interface ExplainApi {
  /** Whether the Explain affordance should be offered (some tier can answer). */
  available: boolean;
  /** Explain one block. `onProgress` fires only on the on-device path while the model downloads. */
  explain: (
    content: string,
    context?: string,
    onProgress?: (progress: DeviceProgress) => void,
  ) => Promise<ExplainOutcome>;
}

// Default: unavailable + a rejecting explain — so a block rendered outside a provider (e.g. an
// isolated test) simply shows no Explain button rather than crashing.
const ExplainContext = createContext<ExplainApi>({
  available: false,
  explain: () => Promise.reject(new Error("Explain is unavailable.")),
});

/** Read the ambient Explain capability (availability + the call). A context module pairs its hook
 *  with its provider, so the fast-refresh "only export components" hint doesn't apply here. */
// eslint-disable-next-line react-refresh/only-export-components
export function useExplainApi(): ExplainApi {
  return useContext(ExplainContext);
}

interface ExplainProviderProps {
  apiBaseUrl: string;
  available: boolean;
  /** Whether this user's LLM runs keyless — only then does the per-device compute choice apply
   *  (a keyed user's explains are always hosted). Default false: today's server-only behavior. */
  llmKeyless?: boolean;
  /** Injectable for tests; production lazily shares the page's one engine (one model download). */
  deviceEngine?: DeviceEngine;
  children: ReactNode;
}

/** Provide the Explain capability: whether it's available and how to call it. The call routes per
 *  request — a keyless user who chose "This device" (and whose browser has WebGPU) is answered by
 *  the local engine, everyone else by the server — so a dropdown change applies immediately. */
export function ExplainProvider({
  apiBaseUrl,
  available,
  llmKeyless = false,
  deviceEngine,
  children,
}: ExplainProviderProps) {
  const value = useMemo<ExplainApi>(
    () => ({
      available,
      explain: async (content, context, onProgress) => {
        if (isDeviceComputeActive(llmKeyless)) {
          const engine = deviceEngine ?? getDeviceEngine();
          const explanation = await engine.explain(content, context, onProgress);
          return { explanation, source: "on-device" };
        }
        return explainBlob(apiBaseUrl, content, context);
      },
    }),
    [apiBaseUrl, available, llmKeyless, deviceEngine],
  );
  return <ExplainContext.Provider value={value}>{children}</ExplainContext.Provider>;
}
