import { useCallback, useState } from "react";

import type { DeviceProgress } from "../../lib/deviceEngine";
import { useExplainApi, type ExplainAnswerSource } from "./ExplainContext";

/** The explain interaction's full state — a discriminated union so impossible combinations
 *  (e.g. an explanation AND an error) cannot be represented. `downloading` only occurs on the
 *  on-device path, while the model's one-time download runs. */
export type ExplainState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "downloading"; progress: number; text: string }
  | { status: "done"; explanation: string; source: ExplainAnswerSource }
  | { status: "error"; message: string };

interface UseExplain {
  /** Whether the affordance should be offered at all (mirrors the ambient capability). */
  available: boolean;
  state: ExplainState;
  /** Run one explanation for the given content; safe to call again after done/error. */
  explain: (content: string, context?: string) => Promise<void>;
}

/** One-shot "explain this block" over the ambient capability, with the standard state arc
 *  (idle → loading [→ downloading…] → done | error). Shared by every reader block. */
export function useExplain(): UseExplain {
  const api = useExplainApi();
  const [state, setState] = useState<ExplainState>({ status: "idle" });

  const explain = useCallback(
    async (content: string, context?: string) => {
      setState({ status: "loading" });
      try {
        const onProgress = (progress: DeviceProgress) =>
          setState({ status: "downloading", progress: progress.progress, text: progress.text });
        const outcome = await api.explain(content, context, onProgress);
        setState({ status: "done", explanation: outcome.explanation, source: outcome.source });
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
