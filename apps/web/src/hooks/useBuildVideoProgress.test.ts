import { renderHook } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useBuildVideoProgress } from "./useBuildVideoProgress";

vi.mock("../lib/videoJobs", () => ({ fetchCourseVideoStatuses: vi.fn() }));
import { fetchCourseVideoStatuses } from "../lib/videoJobs";

const fetchStatuses = vi.mocked(fetchCourseVideoStatuses);
const API = "http://api.test";
const COURSE = "course-1";

function row(jobId: string, status: string) {
  return { jobId, kind: "lesson" as const, lessonId: jobId, status: status as never };
}

// Flush the awaited poll + any rescheduled timer deterministically (no wall-clock waits).
async function tick(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useBuildVideoProgress", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchStatuses.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("reports N-of-M ready while videos are still rendering", async () => {
    fetchStatuses.mockResolvedValue([row("a", "ready"), row("b", "ready"), row("c", "queued")]);

    const { result } = renderHook(() => useBuildVideoProgress(API, COURSE, true, 1000));
    await tick();

    expect(result.current).toEqual({ total: 3, ready: 2, failed: 0, settled: false });
  });

  it("counts failed jobs and settles once every job is terminal", async () => {
    fetchStatuses.mockResolvedValue([row("a", "ready"), row("b", "failed")]);

    const { result } = renderHook(() => useBuildVideoProgress(API, COURSE, true, 1000));
    await tick();

    expect(result.current).toEqual({ total: 2, ready: 1, failed: 1, settled: true });
  });

  it("keeps polling while unsettled, then stops once everything settles", async () => {
    fetchStatuses
      .mockResolvedValueOnce([row("a", "ready"), row("b", "rendering")])
      .mockResolvedValue([row("a", "ready"), row("b", "ready")]);

    const { result } = renderHook(() => useBuildVideoProgress(API, COURSE, true, 1000));
    await tick();
    expect(result.current).toEqual({ total: 2, ready: 1, failed: 0, settled: false });

    await tick(1000); // the interval elapses → it polls again and now everything is ready
    expect(result.current).toEqual({ total: 2, ready: 2, failed: 0, settled: true });
    expect(fetchStatuses).toHaveBeenCalledTimes(2);

    await tick(5000); // well past the interval → no further poll, the loop ended on settle
    expect(fetchStatuses).toHaveBeenCalledTimes(2);
  });

  it("retains the last reading on a transient null read and keeps polling", async () => {
    // Arrange — first poll lands, the second blips (null = a network miss), the third lands settled.
    fetchStatuses
      .mockResolvedValueOnce([row("a", "ready"), row("b", "rendering")])
      .mockResolvedValueOnce(null)
      .mockResolvedValue([row("a", "ready"), row("b", "ready")]);

    const { result } = renderHook(() => useBuildVideoProgress(API, COURSE, true, 1000));
    await tick();
    expect(result.current).toEqual({ total: 2, ready: 1, failed: 0, settled: false });

    await tick(1000); // the null read must NOT revert the canvas to a loading spinner
    expect(result.current).toEqual({ total: 2, ready: 1, failed: 0, settled: false });

    await tick(1000); // the retry lands and everything settles
    expect(result.current).toEqual({ total: 2, ready: 2, failed: 0, settled: true });
    expect(fetchStatuses).toHaveBeenCalledTimes(3);
  });

  it("does not poll while inactive", async () => {
    const { result } = renderHook(() => useBuildVideoProgress(API, COURSE, false, 1000));
    await tick();

    expect(result.current).toBeNull();
    expect(fetchStatuses).not.toHaveBeenCalled();
  });
});
