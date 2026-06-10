import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeRun } from "../test/fixtures";
import { OPENED_RUN_RECHECK_INTERVAL_MS, useOpenedRun } from "./useOpenedRun";

describe("useOpenedRun", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts closed", () => {
    const { result } = renderHook(() => useOpenedRun("http://test"));
    expect(result.current.state.status).toBe("closed");
  });

  it("opens a run's course by id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => makeCourse({ id: "c-1" }) }),
    );
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues" })));

    expect(result.current.state).toMatchObject({ status: "loading", courseId: "c-1" });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-1" });
  });

  it("surfaces a recoverable error when the course is gone (404)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-9", topic: "trees" })));

    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(result.current.state).toMatchObject({
      status: "error",
      courseId: "c-9",
      topic: "trees",
    });
  });

  it("shows a building state for a still-running run without fetching", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues", status: "running" })));

    expect(result.current.state).toMatchObject({
      status: "building",
      courseId: "c-1",
      topic: "queues",
    });
    // A running run has no persisted course yet, so we must not fetch (it would 404).
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("recheck opens the course once a building run has finished", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 }) // first check: build still running
      .mockResolvedValue({ ok: true, json: async () => makeCourse({ id: "c-1" }) }); // then done
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues", status: "running" })));
    expect(result.current.state.status).toBe("building");
    expect(fetchMock).not.toHaveBeenCalled();

    // First re-check fetches; the course isn't persisted yet (404) → stays building, not an error.
    // Gate on the fetch count so this asserts the settled-after-404 building, not the initial one.
    act(() => result.current.recheck());
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.current.state.status).toBe("building");
    });

    // Second re-check: the build finished and the course is persisted → it opens.
    act(() => result.current.recheck());
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-1" });
    });
  });

  it("auto-advances a building run to its finished course without a manual re-check", async () => {
    // The canvas must not get stuck on the building placeholder: while a run is open and still
    // building, the hook re-checks on an interval and flips to the course the moment it persists —
    // quietly, never flashing the loading state over the live timeline.
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 }) // first auto re-check: build still running
      .mockResolvedValue({ ok: true, json: async () => makeCourse({ id: "c-1" }) }); // then done
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues", status: "running" })));
    expect(result.current.state.status).toBe("building");

    // One interval later the poll re-checks; the course isn't persisted yet (404) → stays building,
    // and never flips through `loading` (which would unmount the live timeline).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPENED_RUN_RECHECK_INTERVAL_MS);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.state.status).toBe("building");

    // The next interval finds the persisted course → the canvas advances on its own.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPENED_RUN_RECHECK_INTERVAL_MS);
    });
    expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-1" });

    // Once opened, the poll stops — no further re-checks as more time passes.
    const callsAtReady = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPENED_RUN_RECHECK_INTERVAL_MS * 3);
    });
    expect(fetchMock).toHaveBeenCalledTimes(callsAtReady);
  });

  it("ignores a superseded fetch when a second open lands first", async () => {
    let resolveFirst!: (value: unknown) => void;
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValue({ ok: true, json: async () => makeCourse({ id: "c-2" }) });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useOpenedRun("http://test"));

    // Open c-1 (stays pending), then immediately open c-2 (resolves) — c-2 must win.
    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues" })));
    act(() => result.current.open(makeRun({ id: "c-2", topic: "trees" })));
    await waitFor(() =>
      expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-2" }),
    );

    // Resolving the aborted first fetch must NOT clobber the c-2 result.
    act(() => resolveFirst({ ok: true, json: async () => makeCourse({ id: "c-1" }) }));
    expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-2" });
  });

  it("closes back to the build surface", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => makeCourse() }));
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun()));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.close());

    expect(result.current.state.status).toBe("closed");
  });
});
