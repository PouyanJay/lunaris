import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CourseLoadError } from "../lib/loadCourse";
import type { Course } from "../types/course";
import { useCourseStream } from "./useCourseStream";

const streamCourseMock = vi.hoisted(() => vi.fn());
const fetchCourseByIdMock = vi.hoisted(() => vi.fn());
const fetchRunsMock = vi.hoisted(() => vi.fn());
const fetchRunEventsMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/streamCourse", () => ({ streamCourse: streamCourseMock }));
vi.mock("../lib/runs", () => ({ fetchRuns: fetchRunsMock, fetchRunEvents: fetchRunEventsMock }));
vi.mock("../lib/buildBridge", () => ({ runBuildBridgeWorker: vi.fn(async () => {}) }));
// Keep CourseLoadError + parseCourse real (the hook + tests construct/branch on them); only the
// course-by-id fetch is stubbed.
vi.mock("../lib/loadCourse", async (importActual) => {
  const actual = await importActual<typeof import("../lib/loadCourse")>();
  return { ...actual, fetchCourseById: fetchCourseByIdMock };
});

const COURSE = { id: "course-1", topic: "Graphs" } as unknown as Course;

/** streamCourse reports the run + course ids (as the real one does from the response headers), then
 *  rejects as if the live SSE connection dropped before the terminal course frame. */
function streamDropsAfterIds(): void {
  streamCourseMock.mockImplementation(
    (_base: string, _topic: string, options: { onRunId?: (id: string) => void; onCourseId?: (id: string) => void }) => {
      options.onRunId?.("run-1");
      options.onCourseId?.("course-1");
      return Promise.reject(
        new CourseLoadError("The build stream ended before the course was ready.", {
          streamIncomplete: true,
        }),
      );
    },
  );
}

function run(id: string, status: string) {
  return { id: "course-1", runId: id, status, topic: "Graphs" };
}

beforeEach(() => {
  streamCourseMock.mockReset();
  fetchCourseByIdMock.mockReset();
  fetchRunsMock.mockReset();
  fetchRunEventsMock.mockReset();
  fetchRunEventsMock.mockResolvedValue([]);
});

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("useCourseStream reconnect (SSE drop resilience)", () => {
  it("re-attaches to the durable run when the live stream drops, resolving to the finished course", async () => {
    // Arrange — the stream drops mid-build; the build is still running server-side and its course
    // is already persisted when we poll for it.
    streamDropsAfterIds();
    fetchRunsMock.mockResolvedValue([run("run-1", "running")]);
    fetchCourseByIdMock.mockResolvedValue(COURSE);
    const { result } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert — it lands on the finished course, NOT a broken-build error.
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.state).toMatchObject({ status: "ready", course: COURSE, runId: "run-1" });
    expect(fetchCourseByIdMock).toHaveBeenCalledWith("http://api", "course-1", expect.anything());
  });

  it("marks the build as reconnecting while it re-attaches — never a false error", async () => {
    // Arrange — the course isn't persisted yet (still building) and the run is still running.
    streamDropsAfterIds();
    fetchCourseByIdMock.mockRejectedValue(new CourseLoadError("not found", { status: 404 }));
    fetchRunsMock.mockResolvedValue([run("run-1", "running")]);
    const { result, unmount } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert — it stays in the in-progress (streaming) state, flagged reconnecting; not "error".
    await waitFor(() => {
      expect(result.current.state.status).toBe("streaming");
      expect((result.current.state as { reconnecting: boolean }).reconnecting).toBe(true);
    });
    unmount(); // abort the poll loop
  });

  it("surfaces a real error only when the re-attached run has actually failed", async () => {
    // Arrange — the course never persists (404) because the build failed; the run history says so.
    streamDropsAfterIds();
    fetchCourseByIdMock.mockRejectedValue(new CourseLoadError("not found", { status: 404 }));
    fetchRunsMock.mockResolvedValue([run("run-1", "failed")]);
    const { result } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert — a genuine failure surfaces as an error with an honest message.
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect((result.current.state as { message: string }).message).toMatch(/failed/i);
  });

  it("surfaces a cancelled message when the re-attached run was cancelled", async () => {
    // Arrange — the build was terminated; no course persists and the run history says cancelled.
    streamDropsAfterIds();
    fetchCourseByIdMock.mockRejectedValue(new CourseLoadError("not found", { status: 404 }));
    fetchRunsMock.mockResolvedValue([run("run-1", "cancelled")]);
    const { result } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect((result.current.state as { message: string }).message).toMatch(/cancelled/i);
  });

  it("stops re-attaching and errors on a hard (non-404) course-fetch failure", async () => {
    // Arrange — a definite HTTP failure (e.g. session expired 401) while polling for the course
    // must surface, not spin the reconnect loop forever.
    streamDropsAfterIds();
    fetchCourseByIdMock.mockRejectedValue(new CourseLoadError("unauthorized", { status: 401 }));
    fetchRunsMock.mockResolvedValue([run("run-1", "running")]);
    const { result } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert — surfaced as an error; the run-status check is never reached for this tick.
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(fetchRunsMock).not.toHaveBeenCalled();
  });

  it("still errors immediately on a non-stream-drop failure (no re-attach)", async () => {
    // Arrange — a real server failure, not a transient stream drop (no streamIncomplete flag).
    streamCourseMock.mockImplementation(
      (_base: string, _topic: string, options: { onRunId?: (id: string) => void; onCourseId?: (id: string) => void }) => {
        options.onRunId?.("run-1");
        options.onCourseId?.("course-1");
        return Promise.reject(new CourseLoadError("Course generation failed (HTTP 503)."));
      },
    );
    const { result } = renderHook(() => useCourseStream("http://api"));

    // Act
    act(() => result.current.generate({ topic: "Graphs" }));

    // Assert — straight to error; the reconnect path is never taken.
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(fetchCourseByIdMock).not.toHaveBeenCalled();
    expect(fetchRunsMock).not.toHaveBeenCalled();
  });
});
