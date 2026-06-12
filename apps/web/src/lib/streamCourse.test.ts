import { afterEach, describe, expect, it, vi } from "vitest";

import { courseFrame, makeCourse, progressFrame, sseStreamResponse } from "../test/fixtures";
import { CourseLoadError } from "./loadCourse";
import { streamCourse } from "./streamCourse";

/** Stub global fetch to return an SSE Response streaming the given chunks; returns the mock so
 *  tests can assert on the request it received. */
function stubStream(
  chunks: string[],
  init: { ok?: boolean; status?: number; headers?: Record<string, string> } = {},
) {
  const fetchMock = vi.fn().mockResolvedValue(sseStreamResponse(chunks, init));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("streamCourse", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("emits each progress event in order, then resolves with the final course", async () => {
    stubStream([progressFrame("run_started", 0), progressFrame("graph_built", 1), courseFrame()]);
    const onProgress = vi.fn();

    const course = await streamCourse("http://api", "binary search", { onProgress });

    expect(onProgress).toHaveBeenCalledTimes(2);
    expect(onProgress.mock.calls[0]?.[0]?.stage).toBe("run_started");
    expect(onProgress.mock.calls[1]?.[0]?.stage).toBe("graph_built");
    expect(course.topic).toBe("How binary search works");
  });

  it("reassembles frames split across stream chunks", async () => {
    // The course frame is split mid-way across two chunks.
    const full = progressFrame("run_started", 0) + courseFrame(makeCourse({ id: "split-course" }));
    const cut = Math.floor(full.length / 2);
    stubStream([full.slice(0, cut), full.slice(cut)]);
    const onProgress = vi.fn();

    const course = await streamCourse("http://api", "x", { onProgress });

    expect(onProgress).toHaveBeenCalledTimes(1);
    expect(course.id).toBe("split-course");
  });

  it("throws a CourseLoadError on a non-OK response", async () => {
    stubStream([], { ok: false, status: 503 });

    await expect(streamCourse("http://api", "x", {})).rejects.toBeInstanceOf(CourseLoadError);
  });

  it("throws if the stream ends without a course frame", async () => {
    stubStream([progressFrame("run_started", 0)]);

    await expect(streamCourse("http://api", "x", {})).rejects.toBeInstanceOf(CourseLoadError);
  });

  it("passes the topic and abort signal through to fetch", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseStreamResponse([courseFrame()]));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await streamCourse("http://api", "merge sort", { signal: controller.signal });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/api/courses/stream");
    expect(String(url)).toContain("topic=merge+sort");
    expect(init?.signal).toBe(controller.signal);
  });

  it("passes the device compute choice through as a query param", async () => {
    const fetchMock = stubStream([courseFrame()]);

    await streamCourse("http://api", "x", { compute: "device" });

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("compute=device");
  });

  it("omits the compute param when unset, leaving the API's server default", async () => {
    const fetchMock = stubStream([courseFrame()]);

    await streamCourse("http://api", "x", {});

    expect(String(fetchMock.mock.calls[0]?.[0])).not.toContain("compute=");
  });

  it("reports the run id from the X-Run-Id header before any frame arrives", async () => {
    // The bridge worker must know the run id as soon as the response starts — the first
    // completion can be parked before the first progress frame lands.
    stubStream([progressFrame("run_started", 0), courseFrame()], {
      headers: { "X-Run-Id": "run-123" },
    });
    const arrivals: string[] = [];

    await streamCourse("http://api", "x", {
      onRunId: (runId) => arrivals.push(`run:${runId}`),
      onProgress: () => arrivals.push("progress"),
    });

    expect(arrivals[0]).toBe("run:run-123");
  });
});
