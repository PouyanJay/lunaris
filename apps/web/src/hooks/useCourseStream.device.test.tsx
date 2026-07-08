import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COMPUTE_SOURCE_KEY } from "../lib/computeSource";
import type { DeviceProgress } from "../lib/deviceEngine";
import { useCourseStream } from "./useCourseStream";

const streamCourseMock = vi.hoisted(() => vi.fn());
const workerMock = vi.hoisted(() => vi.fn(async (_options: unknown) => {}));
vi.mock("../lib/streamCourse", () => ({ streamCourse: streamCourseMock }));
vi.mock("../lib/buildBridge", () => ({ runBuildBridgeWorker: workerMock }));

/** A controllable fake engine: preload resolves on demand, reporting one progress beat. */
function fakeEngine(preload = vi.fn(async (onProgress?: (p: DeviceProgress) => void) => {
  onProgress?.({ progress: 0.4, text: "Fetching params" });
})) {
  return { preload, chat: vi.fn(async () => "unused") };
}

function armDeviceChoice() {
  localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
  vi.stubGlobal("navigator", { gpu: {} });
}

describe("useCourseStream device compute", () => {
  beforeEach(() => {
    streamCourseMock.mockReset();
    workerMock.mockReset();
    workerMock.mockResolvedValue(undefined);
  });
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("preloads the engine, streams with compute=device, and serves the bridge", async () => {
    // Arrange — a keyless user with the device choice on capable hardware; the stream
    // reports its run id, then hangs (build in flight).
    armDeviceChoice();
    streamCourseMock.mockImplementation(
      (_base: string, _topic: string, options: { onRunId?: (id: string) => void }) => {
        options.onRunId?.("run-42");
        return new Promise(() => {}); // build still running
      },
    );
    const engine = fakeEngine();
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert — engine prepared first, then the stream carries the device choice and the
    // worker starts against the reported run id with the same engine.
    await waitFor(() => expect(streamCourseMock).toHaveBeenCalled());
    expect(engine.preload).toHaveBeenCalled();
    expect(streamCourseMock.mock.calls[0]?.[2]?.compute).toBe("device");
    await waitFor(() => expect(workerMock).toHaveBeenCalled());
    expect(workerMock.mock.calls[0]?.[0]).toMatchObject({
      apiBaseUrl: "http://api",
      runId: "run-42",
      engine,
      signal: expect.any(AbortSignal), // the build's own controller — aborting it stops the worker
    });
  });

  it("reports model download progress through the preparing state", async () => {
    // Arrange — a preload that reports progress and never finishes (mid-download).
    armDeviceChoice();
    const preload = vi.fn(async (onProgress?: (p: DeviceProgress) => void) => {
      onProgress?.({ progress: 0.4, text: "Fetching params" });
      await new Promise(() => {});
    });
    const engine = fakeEngine(preload);
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert
    await waitFor(() => {
      expect(result.current.state).toMatchObject({
        status: "preparing-device",
        topic: "graphs",
        progress: { progress: 0.4 },
      });
    });
    expect(streamCourseMock).not.toHaveBeenCalled();
  });

  it("fails the build with a clear message when the model can't be prepared", async () => {
    // Arrange — the download dies (offline, out of disk, GPU init failure).
    armDeviceChoice();
    const engine = fakeEngine(vi.fn(async () => Promise.reject(new Error("no space"))));
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert — a recoverable error state; the build never started.
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(streamCourseMock).not.toHaveBeenCalled();
  });

  it("carries the full request on the error state so a retry re-runs the identical build", async () => {
    // Arrange — a device build that fails to prepare, requested with every build option set: a
    // confirmed clarification, a non-default depth, and the Official-sources-only switch on.
    armDeviceChoice();
    const engine = fakeEngine(vi.fn(async () => Promise.reject(new Error("no space"))));
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );
    const request = {
      topic: "graphs",
      clarification: { targetLevel: "advanced" as const },
      discoveryDepth: "thorough" as const,
      officialOnly: true,
    };

    // Act
    act(() => result.current.generate(request));

    // Assert — the error state preserves every build option (retry parity: clarification, depth,
    // AND official_only — the full class of fields the retry bug dropped).
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    const state = result.current.state;
    if (state.status !== "error") throw new Error("expected the error state");
    expect(state.request).toEqual(request);
  });

  it("explains a failed device build in terms of the tab-open contract", async () => {
    // Arrange — the stream dies without a course (the server failed the run — e.g. this tab
    // went silent after a laptop sleep and the bridge disconnected it).
    armDeviceChoice();
    const { CourseLoadError } = await import("../lib/loadCourse");
    streamCourseMock.mockImplementation(
      (_base: string, _topic: string, options: { onRunId?: (id: string) => void }) => {
        options.onRunId?.("run-42");
        return Promise.reject(
          new CourseLoadError("The build stream ended before the course was ready."),
        );
      },
    );
    const engine = fakeEngine();
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert — the error names the likely cause, not just a generic stream failure.
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    const state = result.current.state as { status: "error"; message: string };
    expect(state.message).toMatch(/keeping the tab open/i);
  });

  it("falls back to a server build when the saved device choice has no WebGPU", async () => {
    // Arrange — a stale "device" choice carried to a browser that can't run it (no navigator.gpu
    // stub: jsdom is the realistic unsupported browser). No dead end: the build still runs.
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
    streamCourseMock.mockImplementation(async () => new Promise(() => {}));
    const engine = fakeEngine();
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert — straight to a server stream: no preload, no compute param, no worker.
    await waitFor(() => expect(streamCourseMock).toHaveBeenCalled());
    expect(engine.preload).not.toHaveBeenCalled();
    expect(streamCourseMock.mock.calls[0]?.[2]?.compute).toBeUndefined();
    expect(workerMock).not.toHaveBeenCalled();
  });

  it("builds on the server when the user is keyed, even with a saved device choice", async () => {
    // Arrange
    armDeviceChoice();
    streamCourseMock.mockImplementation(async () => new Promise(() => {}));
    const engine = fakeEngine();
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: false, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));

    // Assert — no preload, no compute param, no worker: today's hosted build untouched.
    await waitFor(() => expect(streamCourseMock).toHaveBeenCalled());
    expect(engine.preload).not.toHaveBeenCalled();
    expect(streamCourseMock.mock.calls[0]?.[2]?.compute).toBeUndefined();
    expect(workerMock).not.toHaveBeenCalled();
  });

  it("abandons a device build cleanly when reset during preparation", async () => {
    // Arrange — reset() fires while the model is still downloading.
    armDeviceChoice();
    const preload = vi.fn(
      async (_onProgress?: (p: DeviceProgress) => void): Promise<void> =>
        new Promise<void>(() => {}),
    );
    const engine = fakeEngine(preload);
    const { result } = renderHook(() =>
      useCourseStream("http://api", { llmKeyless: true, deviceEngine: engine }),
    );

    // Act
    act(() => result.current.generate({ topic: "graphs" }));
    await waitFor(() => expect(result.current.state.status).toBe("preparing-device"));
    act(() => result.current.reset());

    // Assert — back to idle; the abandoned preparation never starts a stream.
    expect(result.current.state.status).toBe("idle");
    expect(streamCourseMock).not.toHaveBeenCalled();
  });
});
