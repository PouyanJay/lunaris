import { useCallback, useEffect, useRef, useState } from "react";

import { CorpusError, fetchCorpusSources } from "../lib/corpus";
import type { CorpusSource } from "../types/course";

export type CorpusState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; sources: CorpusSource[] }
  | { status: "error"; message: string };

interface Corpus {
  state: CorpusState;
  reload: () => void;
}

/** Load a course's grounding-corpus sources, with reload (used after an add/delete). */
export function useCorpus(apiBaseUrl: string, courseId: string): Corpus {
  const [state, setState] = useState<CorpusState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: "loading" });

    fetchCorpusSources(apiBaseUrl, courseId, controller.signal)
      .then((sources) => {
        if (controller.signal.aborted) return;
        setState(sources.length === 0 ? { status: "empty" } : { status: "ready", sources });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof CorpusError ? error.message : "Couldn't load the corpus.";
        setState({ status: "error", message });
      });
  }, [apiBaseUrl, courseId]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { state, reload: load };
}
