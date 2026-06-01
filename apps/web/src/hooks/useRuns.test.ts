import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeRun } from "../test/fixtures";
import { RUNS_POLL_INTERVAL_MS, useRuns, type RunsState } from "./useRuns";

/** Narrow to the ready runs with a clear failure message if the state isn't ready. */
function readyRuns(state: RunsState) {
  if (state.status !== "ready") throw new Error(`expected ready state, got "${state.status}"`);
  return state.runs;
}

describe("useRuns", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("loads recent runs from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRun({ topic: "graphs" })] }),
    );

    const { result } = renderHook(() => useRuns("http://test"));

    expect(result.current.state.status).toBe("loading");
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(readyRuns(result.current.state)).toEqual([expect.objectContaining({ topic: "graphs" })]);
  });

  it("surfaces a recoverable error when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    const { result } = renderHook(() => useRuns("http://test"));

    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(result.current.state).toMatchObject({ status: "error" });
  });

  it("re-fetches on reload", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValue({ ok: true, json: async () => [makeRun()] });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRuns("http://test"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(readyRuns(result.current.state)).toHaveLength(0);

    act(() => result.current.reload());

    await waitFor(() => expect(readyRuns(result.current.state)).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the prior runs visible while a reload is in flight (stale-while-revalidate)", async () => {
    let resolveReload!: (value: unknown) => void;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [makeRun({ topic: "graphs" })] })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReload = resolve;
          }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRuns("http://test"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.reload());

    // While the refresh is pending, the stale list stays visible — never a skeleton flash.
    expect(result.current.state.status).toBe("ready");
    expect(readyRuns(result.current.state)).toHaveLength(1);

    act(() => resolveReload({ ok: true, json: async () => [] }));
    await waitFor(() => expect(readyRuns(result.current.state)).toHaveLength(0));
  });

  it("polls the run history while a build is running and stops once it finishes", async () => {
    // A live build's status must refresh without a manual reload: while the list holds a running
    // run the hook re-fetches on an interval, and once nothing is running it stops polling.
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [makeRun({ status: "running" })] })
      .mockResolvedValue({ ok: true, json: async () => [makeRun({ status: "completed" })] });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRuns("http://test"));

    // Initial load lands a still-running run, which starts the live-status poll.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(readyRuns(result.current.state)[0]?.status).toBe("running");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // One interval later the poll re-reads and sees the run has finished.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUNS_POLL_INTERVAL_MS);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(readyRuns(result.current.state)[0]?.status).toBe("completed");

    // With nothing running, polling stops — no further reads as more time passes.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUNS_POLL_INTERVAL_MS * 3);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the stale runs when a background refresh fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [makeRun({ topic: "graphs" })] })
      .mockResolvedValueOnce({ ok: false, status: 503 });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRuns("http://test"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.reload());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // A failed refresh keeps the prior list rather than blanking it to an error.
    expect(result.current.state.status).toBe("ready");
    expect(readyRuns(result.current.state)).toHaveLength(1);
  });
});
