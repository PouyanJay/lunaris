import { useCallback, useState } from "react";

import { useExplainApi } from "./ExplainContext";

/** The explain interaction's full state — a discriminated union so impossible combinations
 *  (e.g. an explanation AND an error) cannot be represented. */
export type ExplainState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; explanation: string }
  | { status: "error"; message: string };

interface UseExplain {
  /** Whether the affordance should be offered at all (mirrors the ambient capability). */
  available: boolean;
  state: ExplainState;
  /** Run one explanation for the given content; safe to call again after done/error. */
  explain: (content: string, context?: string) => Promise<void>;
}

/** One-shot "explain this block" over the ambient capability, with the standard state arc
 *  (idle → loading → done | error). Shared by every reader block that offers Explain. */
export function useExplain(): UseExplain {
  const api = useExplainApi();
  const [state, setState] = useState<ExplainState>({ status: "idle" });

  const explain = useCallback(
    async (content: string, context?: string) => {
      setState({ status: "loading" });
      try {
        const explanation = await api.explain(content, context);
        setState({ status: "done", explanation });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Couldn't generate an explanation right now.";
        setState({ status: "error", message });
      }
    },
    [api],
  );

  return { available: api.available, state, explain };
}
