import { createContext, useContext, useMemo, type ReactNode } from "react";

import { explainBlob } from "../../lib/explain";

interface ExplainApi {
  /** Whether the Explain affordance should be offered (an Anthropic key is reachable). */
  available: boolean;
  /** Ask the API to explain a blob in plain language; rejects on failure. */
  explain: (content: string, context?: string) => Promise<string>;
}

// Default: unavailable + a rejecting explain — so a JsonArtifact rendered outside a provider (e.g.
// an isolated test) simply shows no Explain button rather than crashing.
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
  children: ReactNode;
}

/** Provide the Explain capability to the transcript: whether it's available and how to call it. */
export function ExplainProvider({ apiBaseUrl, available, children }: ExplainProviderProps) {
  const value = useMemo<ExplainApi>(
    () => ({ available, explain: (content, context) => explainBlob(apiBaseUrl, content, context) }),
    [apiBaseUrl, available],
  );
  return <ExplainContext.Provider value={value}>{children}</ExplainContext.Provider>;
}
