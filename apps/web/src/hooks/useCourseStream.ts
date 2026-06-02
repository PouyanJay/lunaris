import { useCallback, useEffect, useRef, useState } from "react";

import type { StageTimes } from "../lib/buildTimeline";
import { CourseLoadError } from "../lib/loadCourse";
import { streamCourse } from "../lib/streamCourse";
import type { AgentEvent, Course, ProgressEvent } from "../types/course";

export type BuildState =
  | { status: "idle" }
  | {
      status: "streaming";
      topic: string;
      events: ProgressEvent[];
      agentEvents: AgentEvent[];
      // The run_id, captured from the first event — lets the UI terminate this build by run_id and
      // (once ready) replay it in the Build tab. Undefined until the first event arrives.
      runId: string | undefined;
      // Client-stamped stage arrival times (wall-clock), for the timeline's per-phase durations.
      stageTimes: StageTimes;
    }
  // runId is carried from the streaming state so the ready course's Build tab can replay this run.
  | { status: "ready"; course: Course; runId: string | undefined }
  | { status: "error"; message: string; topic: string };

interface CourseStream {
  state: BuildState;
  /** Start (or restart) a live build for `topic`. */
  generate: (topic: string) => void;
  /** Abort any in-flight build and return to the idle topic form. */
  reset: () => void;
}

/**
 * Drives the live course build: idle → streaming (progress events accumulate) → ready
 * (the finished course) or error. Each `generate` aborts any prior in-flight build, so
 * starting a new topic never leaves a stale stream running; the controller is also
 * aborted on unmount.
 */
export function useCourseStream(apiBaseUrl: string): CourseStream {
  const [state, setState] = useState<BuildState>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const generate = useCallback(
    (topic: string) => {
      abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({
        status: "streaming",
        topic,
        events: [],
        agentEvents: [],
        runId: undefined,
        stageTimes: {},
      });

      streamCourse(apiBaseUrl, topic, {
        signal: controller.signal,
        onProgress: (event) => {
          // Stamp the stage's wall-clock arrival now (not in the reducer, which may run twice in
          // StrictMode); the latest arrival per stage wins, so a repeated stage reflects its last beat.
          const arrivedAt = Date.now();
          setState((prev) =>
            prev.status === "streaming"
              ? {
                  ...prev,
                  runId: prev.runId ?? event.runId,
                  events: [...prev.events, event],
                  stageTimes: { ...prev.stageTimes, [event.stage]: arrivedAt },
                }
              : prev,
          );
        },
        onAgent: (event) =>
          setState((prev) =>
            prev.status === "streaming"
              ? {
                  ...prev,
                  runId: prev.runId ?? event.runId,
                  agentEvents: [...prev.agentEvents, event],
                }
              : prev,
          ),
      })
        .then((course) => {
          if (controller.signal.aborted) return;
          // Carry the run_id captured during streaming into ready, so the Build tab can replay it.
          setState((prev) => ({
            status: "ready",
            course,
            runId: prev.status === "streaming" ? prev.runId : undefined,
          }));
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          const message =
            error instanceof CourseLoadError
              ? error.message
              : "An unexpected error occurred while building the course.";
          setState({ status: "error", message, topic });
        });
    },
    [apiBaseUrl, abort],
  );

  const reset = useCallback(() => {
    abort();
    setState({ status: "idle" });
  }, [abort]);

  useEffect(() => abort, [abort]);

  return { state, generate, reset };
}
