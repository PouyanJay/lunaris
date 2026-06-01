import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeRun } from "../test/fixtures";
import { useOpenedRun } from "./useOpenedRun";

describe("useOpenedRun", () => {
  afterEach(() => vi.unstubAllGlobals());

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
