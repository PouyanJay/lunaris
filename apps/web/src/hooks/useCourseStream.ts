import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { StageTimes } from "../lib/buildTimeline";
import { runBuildBridgeWorker } from "../lib/buildBridge";
import { isDeviceComputeActive } from "../lib/computeSource";
import {
  getDeviceEngine,
  type ChatBackend,
  type DeviceProgress,
} from "../lib/deviceEngine";
import { CourseLoadError } from "../lib/loadCourse";
import { streamCourse } from "../lib/streamCourse";
import type { Clarification } from "../types/clarifier";
import type { AgentEvent, Course, DiscoveryDepth, ProgressEvent } from "../types/course";

export type BuildState =
  | { status: "idle" }
  // A device-compute build front-loads the on-device model download (with real progress) BEFORE
  // the build starts, so the server never waits out a first-time ~1.8 GB fetch mid-run.
  | { status: "preparing-device"; topic: string; progress: DeviceProgress | null }
  | {
      status: "streaming";
      topic: string;
      events: ProgressEvent[];
      agentEvents: AgentEvent[];
      // The run_id, captured from the X-Run-Id header (or the first event) — lets the UI terminate
      // this build by run_id and (once ready) replay it in the Build tab; on a device build it is
      // also what the bridge worker polls. Undefined until known.
      runId: string | undefined;
      // Client-stamped stage arrival times (wall-clock), for the timeline's per-phase durations.
      stageTimes: StageTimes;
      // Whether THIS tab is serving the build's completions. Captured at generate time — the
      // dropdown can change mid-build without changing where the running build computes — and
      // rendered as the in-build "keep this tab open" notice.
      servedByThisDevice: boolean;
    }
  // runId is carried from the streaming state so the ready course's Build tab can replay this run.
  | { status: "ready"; course: Course; runId: string | undefined }
  // discoveryDepth is carried so a retry re-runs at the depth the learner chose, not the default.
  | { status: "error"; message: string; topic: string; discoveryDepth: DiscoveryDepth };

/** The engine slice the build flow needs: the bridge's chat plus the front-loaded download. */
export interface BuildDeviceEngine extends ChatBackend {
  preload(onProgress?: (progress: DeviceProgress) => void): Promise<void>;
}

interface CourseStreamOptions {
  /** Whether this user's LLM runs keyless — only then can the device compute choice apply
   *  (a keyed user's builds are always hosted). Default false: today's behavior. */
  llmKeyless?: boolean;
  /** Injectable for tests; production lazily shares the page's one engine (one model download). */
  deviceEngine?: BuildDeviceEngine;
}

interface CourseStream {
  state: BuildState;
  /** Start (or restart) a live build for `topic`, optionally with the learner's confirm answers. */
  generate: (topic: string, clarification?: Clarification, discoveryDepth?: DiscoveryDepth) => void;
  /** Abort any in-flight build and return to the idle topic form. */
  reset: () => void;
}

type SetBuildState = Dispatch<SetStateAction<BuildState>>;

/** Fold one pipeline-stage event into the streaming state. `arrivedAt` is stamped by the caller
 *  (not here, where StrictMode may run the reducer twice); the latest arrival per stage wins. */
function applyProgressEvent(prev: BuildState, event: ProgressEvent, arrivedAt: number): BuildState {
  if (prev.status !== "streaming") return prev;
  return {
    ...prev,
    runId: prev.runId ?? event.runId,
    events: [...prev.events, event],
    stageTimes: { ...prev.stageTimes, [event.stage]: arrivedAt },
  };
}

/** Fold one agent-transcript beat into the streaming state. */
function applyAgentEvent(prev: BuildState, event: AgentEvent): BuildState {
  if (prev.status !== "streaming") return prev;
  return { ...prev, runId: prev.runId ?? event.runId, agentEvents: [...prev.agentEvents, event] };
}

interface StreamBuildOptions {
  apiBaseUrl: string;
  topic: string;
  clarification: Clarification | undefined;
  discoveryDepth: DiscoveryDepth | undefined;
  /** Non-null = a device build: stream with compute=device and serve the bridge from this tab. */
  engine: BuildDeviceEngine | null;
  controller: AbortController;
  setState: SetBuildState;
}

/** Run one build stream to its terminal state (ready/error), serving the bridge when `engine`
 *  is present. Module-level (not a closure in the hook) so every input is an explicit parameter. */
function streamBuild(options: StreamBuildOptions): void {
  const { apiBaseUrl, topic, clarification, discoveryDepth, engine, controller, setState } = options;
  setState({
    status: "streaming",
    topic,
    events: [],
    agentEvents: [],
    runId: undefined,
    stageTimes: {},
    servedByThisDevice: engine !== null,
  });
  streamCourse(apiBaseUrl, topic, {
    ...(clarification ? { clarification } : {}),
    ...(discoveryDepth ? { discoveryDepth } : {}),
    ...(engine ? { compute: "device" as const } : {}),
    signal: controller.signal,
    onRunId: (runId) => {
      if (engine && !controller.signal.aborted) {
        // The worker stops on its own when the run ends (404) or this build is aborted. A worker
        // failure is the server's to handle (liveness fails the run, surfacing via the stream);
        // the debug trace just keeps a broken worker diagnosable.
        runBuildBridgeWorker({ apiBaseUrl, runId, engine, signal: controller.signal }).catch(
          (error: unknown) => console.debug("build bridge worker stopped", error),
        );
      }
      setState((prev) =>
        prev.status === "streaming" ? { ...prev, runId: prev.runId ?? runId } : prev,
      );
    },
    onProgress: (event) => {
      const arrivedAt = Date.now();
      setState((prev) => applyProgressEvent(prev, event, arrivedAt));
    },
    onAgent: (event) => setState((prev) => applyAgentEvent(prev, event)),
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
      const message = buildFailureMessage(error, engine !== null);
      setState({ status: "error", message, topic, discoveryDepth: discoveryDepth ?? "standard" });
    });
}

/** The learner-facing failure copy. A device build's stream most often dies because this tab
 *  broke the tab-open contract (closed/slept → the server disconnected the bridge), so its
 *  message names that cause and both ways out — the generic stream error alone would read as a
 *  server fault. */
function buildFailureMessage(error: unknown, onDevice: boolean): string {
  if (!(error instanceof CourseLoadError)) {
    return "An unexpected error occurred while building the course.";
  }
  if (!onDevice) return error.message;
  return (
    `${error.message} This build was running on your device — if this tab was closed or the ` +
    "device slept, the build lost its model. Retry keeping the tab open, or switch the Draft " +
    "AI back to the Lunaris server."
  );
}

/** Download + boot the on-device model, then hand off to the stream; a failed preparation is a
 *  recoverable error state, never a build that starts without its model. */
function prepareDeviceThenStream(options: StreamBuildOptions & { engine: BuildDeviceEngine }): void {
  const { engine, controller, setState, topic, discoveryDepth } = options;
  setState({ status: "preparing-device", topic, progress: null });
  engine
    .preload((progress) => {
      if (controller.signal.aborted) return;
      setState((prev) => (prev.status === "preparing-device" ? { ...prev, progress } : prev));
    })
    .then(() => {
      if (controller.signal.aborted) return;
      streamBuild(options);
    })
    .catch(() => {
      if (controller.signal.aborted) return;
      setState({
        status: "error",
        message:
          "The on-device model could not be prepared. Check your connection and free disk " +
          "space, or switch the compute choice back to the Lunaris server.",
        topic,
        discoveryDepth: discoveryDepth ?? "standard",
      });
    });
}

/**
 * Drives the live course build: idle → streaming (progress events accumulate) → ready
 * (the finished course) or error. A keyless build whose learner chose "This device" first
 * prepares the on-device model (preparing-device, with download progress), then streams with
 * `compute=device` while this tab serves the run's completions over the build bridge.
 * Each `generate` aborts any prior in-flight build, so starting a new topic never leaves a
 * stale stream (or bridge worker) running; the controller is also aborted on unmount.
 */
export function useCourseStream(
  apiBaseUrl: string,
  { llmKeyless = false, deviceEngine }: CourseStreamOptions = {},
): CourseStream {
  const [state, setState] = useState<BuildState>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const generate = useCallback(
    (topic: string, clarification?: Clarification, discoveryDepth?: DiscoveryDepth) => {
      abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      const onDevice = isDeviceComputeActive(llmKeyless);
      const engine = onDevice ? (deviceEngine ?? getDeviceEngine()) : null;
      const options = {
        apiBaseUrl,
        topic,
        clarification,
        discoveryDepth,
        engine,
        controller,
        setState,
      };
      if (engine === null) {
        streamBuild(options);
        return;
      }
      prepareDeviceThenStream({ ...options, engine });
    },
    [apiBaseUrl, abort, llmKeyless, deviceEngine],
  );

  const reset = useCallback(() => {
    abort();
    setState({ status: "idle" });
  }, [abort]);

  useEffect(() => abort, [abort]);

  return { state, generate, reset };
}
