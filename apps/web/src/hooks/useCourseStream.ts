import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { StageTimes } from "../lib/buildTimeline";
import { runBuildBridgeWorker } from "../lib/buildBridge";
import { isDeviceComputeActive } from "../lib/computeSource";
import {
  getDeviceEngine,
  type ChatBackend,
  type DeviceProgress,
} from "../lib/deviceEngine";
import { CourseLoadError, fetchCourseById } from "../lib/loadCourse";
import { fetchRunEvents, fetchRuns } from "../lib/runs";
import { splitRunEvents } from "../lib/splitRunEvents";
import { streamCourse } from "../lib/streamCourse";
import type { Clarification } from "../types/clarifier";
import type { AgentEvent, Course, DiscoveryDepth, ProgressEvent } from "../types/course";

/** The parameters of one build, carried as a single object so adding a build option doesn't grow
 *  every call site's argument list. Threaded from the composer's Generate → `generate()` → the SSE
 *  request, and stashed on the error state so a retry re-runs the identical build (topic +
 *  clarification + depth + trust switch). */
export interface BuildRequest {
  topic: string;
  clarification?: Clarification | undefined;
  discoveryDepth?: DiscoveryDepth | undefined;
  officialOnly?: boolean | undefined;
}

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
      // The course_id, captured from the X-Course-Id header — the key to re-attach to the durable
      // build (poll its finished course) if the live SSE stream drops. Undefined until known.
      courseId: string | undefined;
      // Client-stamped stage arrival times (wall-clock), for the timeline's per-phase durations.
      stageTimes: StageTimes;
      // Whether THIS tab is serving the build's completions. Captured at generate time — the
      // dropdown can change mid-build without changing where the running build computes — and
      // rendered as the in-build "keep this tab open" notice.
      servedByThisDevice: boolean;
      // True once the live SSE stream dropped and we re-attached to the durable run by polling its
      // persisted event log + finished course. The build never stopped; only the live feed did.
      reconnecting: boolean;
    }
  // runId is carried from the streaming state so the ready course's Build tab can replay this run.
  | { status: "ready"; course: Course; runId: string | undefined }
  // The full request is carried so a retry re-runs the identical build (same depth/level/trust),
  // not a defaulted one.
  | { status: "error"; message: string; request: BuildRequest };

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
  /** Start (or restart) a live build from a request (topic + optional clarification, depth, and the
   *  "Official sources only" switch). */
  generate: (request: BuildRequest) => void;
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
  request: BuildRequest;
  /** Non-null = a device build: stream with compute=device and serve the bridge from this tab. */
  engine: BuildDeviceEngine | null;
  controller: AbortController;
  setState: SetBuildState;
}

/** Run one build stream to its terminal state (ready/error), serving the bridge when `engine`
 *  is present. Module-level (not a closure in the hook) so every input is an explicit parameter. */
function streamBuild(options: StreamBuildOptions): void {
  const { apiBaseUrl, request, engine, controller, setState } = options;
  const { topic, clarification, discoveryDepth, officialOnly } = request;
  // Captured from the response headers for the reconnect path: closures over local lets, since the
  // .catch needs them and they land before any frame (so they're set well before a drop).
  let runId: string | undefined;
  let courseId: string | undefined;
  setState({
    status: "streaming",
    topic,
    events: [],
    agentEvents: [],
    runId: undefined,
    courseId: undefined,
    stageTimes: {},
    servedByThisDevice: engine !== null,
    reconnecting: false,
  });
  streamCourse(apiBaseUrl, topic, {
    ...(clarification ? { clarification } : {}),
    ...(discoveryDepth ? { discoveryDepth } : {}),
    ...(officialOnly ? { officialOnly } : {}),
    ...(engine ? { compute: "device" as const } : {}),
    signal: controller.signal,
    onRunId: (id) => {
      runId = id;
      if (engine && !controller.signal.aborted) {
        // The worker stops on its own when the run ends (404) or this build is aborted. A worker
        // failure is the server's to handle (liveness fails the run, surfacing via the stream);
        // the debug trace just keeps a broken worker diagnosable.
        runBuildBridgeWorker({ apiBaseUrl, runId: id, engine, signal: controller.signal }).catch(
          (error: unknown) => console.debug("build bridge worker stopped", error),
        );
      }
      setState((prev) =>
        prev.status === "streaming" ? { ...prev, runId: prev.runId ?? id } : prev,
      );
    },
    onCourseId: (id) => {
      courseId = id;
      setState((prev) =>
        prev.status === "streaming" ? { ...prev, courseId: prev.courseId ?? id } : prev,
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
      // A server build whose live stream dropped before the course arrived is very likely a
      // transient disconnect — the build is a durable server task that keeps running. Re-attach to
      // it instead of falsely reporting a broken build. A device build can't (its model lives in
      // this tab, which the stream drop implicates), so it falls through to the error state.
      if (
        engine === null &&
        error instanceof CourseLoadError &&
        error.streamIncomplete &&
        runId &&
        courseId
      ) {
        void reconnectBuild({
          apiBaseUrl,
          runId,
          courseId,
          request,
          controller,
          setState,
        });
        return;
      }
      const message = buildFailureMessage(error, engine !== null);
      setState({ status: "error", message, request });
    });
}

/** How often a reconnected build re-checks the durable run (mirrors the opened-run recheck): it
 *  refreshes the live timeline from the event log, finishes when the course persists, and gives up
 *  only when the run itself ends failed/cancelled. */
export const BUILD_RECONNECT_POLL_INTERVAL_MS = 3000;

interface ReconnectOptions {
  apiBaseUrl: string;
  runId: string;
  courseId: string;
  request: BuildRequest;
  controller: AbortController;
  setState: SetBuildState;
}

/**
 * Re-attach to a build whose live SSE stream dropped before the course arrived. The build is a
 * durable server task that keeps running, so instead of reporting an error we poll the persisted
 * run: keep the timeline advancing from the event log, resolve to the finished course once it
 * persists, and surface a real error only when the run itself ends failed/cancelled. Polling stops
 * on the controller's abort (a new build, reset, or unmount).
 */
async function reconnectBuild(options: ReconnectOptions): Promise<void> {
  const { apiBaseUrl, runId, courseId, request, controller, setState } = options;
  const { signal } = controller;
  setState((prev) => (prev.status === "streaming" ? { ...prev, reconnecting: true } : prev));

  while (!signal.aborted) {
    // Keep the live timeline advancing from the durable event log (best-effort; a blip retries
    // next tick). Don't clobber the shown timeline with an empty read while the log write lags.
    try {
      const rows = await fetchRunEvents(apiBaseUrl, runId, signal);
      if (signal.aborted) return;
      if (rows.length > 0) {
        const { events, agentEvents } = splitRunEvents(rows);
        setState((prev) => (prev.status === "streaming" ? { ...prev, events, agentEvents } : prev));
      }
    } catch {
      // transient — the next tick retries
    }

    // The build persists its course only on success: a successful fetch is the completion signal.
    try {
      const course = await fetchCourseById(apiBaseUrl, courseId, signal);
      if (signal.aborted) return;
      setState({ status: "ready", course, runId });
      return;
    } catch (error) {
      if (signal.aborted) return;
      // 404 = still building, and a transport error (no status) = a transient blip — both keep
      // polling. A definite non-404 HTTP status (e.g. 401 session expired, 5xx) is a real failure:
      // surface it rather than spin the loop forever.
      const status = error instanceof CourseLoadError ? error.status : undefined;
      if (status !== undefined && status !== 404) {
        setState({
          status: "error",
          message:
            error instanceof CourseLoadError
              ? error.message
              : "An unexpected error occurred while building the course.",
          request,
        });
        return;
      }
    }

    // No course yet: only a terminal run status (failed/cancelled) ends the wait with an error.
    try {
      const runs = await fetchRuns(apiBaseUrl, signal);
      if (signal.aborted) return;
      const run = runs.find((candidate) => candidate.runId === runId);
      if (run && (run.status === "failed" || run.status === "cancelled")) {
        setState({
          status: "error",
          message:
            run.status === "cancelled"
              ? "This build was cancelled."
              : "The build failed before the course was ready.",
          request,
        });
        return;
      }
    } catch {
      // run-history blip — keep waiting on the course
    }

    await abortableDelay(BUILD_RECONNECT_POLL_INTERVAL_MS, signal);
  }
}

/** A `setTimeout` that also settles immediately when `signal` aborts, so a pending reconnect tick
 *  never outlives the build it belongs to (a new build, reset, or unmount). */
function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
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
  const { engine, controller, setState, request } = options;
  setState({ status: "preparing-device", topic: request.topic, progress: null });
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
        request,
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
    (request: BuildRequest) => {
      abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      const onDevice = isDeviceComputeActive(llmKeyless);
      const engine = onDevice ? (deviceEngine ?? getDeviceEngine()) : null;
      const options = { apiBaseUrl, request, engine, controller, setState };
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
