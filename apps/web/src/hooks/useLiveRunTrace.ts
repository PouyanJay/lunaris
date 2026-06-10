import { useCallback, useEffect, useRef, useState } from "react";

import { fetchRunEvents, RunsError } from "../lib/runs";
import { splitRunEvents } from "../lib/splitRunEvents";
import type { AgentEvent, ProgressEvent } from "../types/course";

export type LiveRunTraceState =
  | { status: "loading" }
  // The run's log so far, re-fetched on an interval while it is still in flight. `done` is true once
  // the log shows the terminal `run_completed` event — the log is then final and polling stops.
  | { status: "streaming"; events: ProgressEvent[]; agentEvents: AgentEvent[]; done: boolean }
  | { status: "error"; message: string };

interface LiveRunTrace {
  state: LiveRunTraceState;
  /** Re-fetch the in-flight build log now (aborts any in-flight load first). */
  reload: () => void;
}

/** How often to re-poll a running build's event log so a reattached view tracks live progress
 *  without an SSE. Matches the run-history poll cadence so the two stay in step. */
export const LIVE_RUN_TRACE_POLL_INTERVAL_MS = 2500;

/** The run's log is final once it records the terminal completion stage — no need to keep polling. */
function isComplete(events: ProgressEvent[]): boolean {
  return events.some((event) => event.stage === "run_completed");
}

/**
 * Reattaches to a still-running build by polling its persisted event log, so returning to an
 * in-flight run (reload / navigate / a dropped SSE) shows live progress instead of a static
 * placeholder. Unlike {@link useRunTrace} (a one-shot static replay), this re-fetches on an interval
 * — stale-while-revalidate so the timeline never blanks between polls, and an empty log reads as
 * "streaming, nothing yet" rather than "no record" (a live run simply hasn't emitted yet). Polling
 * stops once the log records completion; a missing `runId` resolves straight to a done, empty stream.
 */
export function useLiveRunTrace(apiBaseUrl: string, runId: string | undefined): LiveRunTrace {
  const [state, setState] = useState<LiveRunTraceState>({ status: "loading" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    controllerRef.current?.abort();
    if (!runId) {
      // No run to attach to — nothing to stream. A done, empty stream lets the caller fall back.
      setState({ status: "streaming", events: [], agentEvents: [], done: true });
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;

    fetchRunEvents(apiBaseUrl, runId, controller.signal)
      .then((rows) => {
        if (controller.signal.aborted) return;
        const { events, agentEvents } = splitRunEvents(rows);
        setState({ status: "streaming", events, agentEvents, done: isComplete(events) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof RunsError ? error.message : "Couldn't load this build.";
        // Stale-while-revalidate: a background-poll failure keeps the timeline already shown and
        // keeps polling (a transient blip on a slow box recovers); surface an error only on the
        // first load, when there is nothing to fall back to.
        setState((prev) => (prev.status === "streaming" ? prev : { status: "error", message }));
      });
  }, [apiBaseUrl, runId]);

  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);

  // Poll while the run is still live. The flag is a stable boolean (true until the log completes),
  // so the interval is created once when streaming begins and torn down once it is done — not per
  // poll, even though each poll replaces the events array.
  const isLive = state.status === "streaming" && !state.done;
  useEffect(() => {
    if (!isLive) return undefined;
    const interval = setInterval(load, LIVE_RUN_TRACE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isLive, load]);

  return { state, reload: load };
}
