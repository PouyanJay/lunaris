import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeAgentEvent, makeProgressEvent, makeRunEvent } from "../test/fixtures";
import { LIVE_RUN_TRACE_POLL_INTERVAL_MS, useLiveRunTrace } from "./useLiveRunTrace";

function stubFetch(value: { ok: boolean; status?: number; json?: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, ...value }));
}

describe("useLiveRunTrace", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("streams the in-flight log, treating an empty log as 'nothing yet' (not 'no record')", async () => {
    stubFetch({ ok: true, json: async () => [] });

    const { result } = renderHook(() => useLiveRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("streaming"));
    const state = result.current.state;
    if (state.status !== "streaming") throw new Error("expected streaming");
    expect(state.events).toHaveLength(0);
    expect(state.agentEvents).toHaveLength(0);
    expect(state.done).toBe(false);
  });

  it("splits the persisted log into the two timeline streams", async () => {
    stubFetch({
      ok: true,
      json: async () => [
        makeRunEvent(0, makeProgressEvent("run_started", 0)),
        makeRunEvent(1, makeAgentEvent("reasoning", 0, { text: "Planning…" })),
        makeRunEvent(2, makeProgressEvent("concepts_extracted", 1)),
      ],
    });

    const { result } = renderHook(() => useLiveRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("streaming"));
    const state = result.current.state;
    if (state.status !== "streaming") throw new Error("expected streaming");
    expect(state.events).toHaveLength(2);
    expect(state.agentEvents).toHaveLength(1);
    expect(state.done).toBe(false);
  });

  it("polls while running, then stops once the log records completion", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [makeRunEvent(0, makeProgressEvent("run_started", 0))],
      })
      .mockResolvedValue({
        ok: true,
        json: async () => [
          makeRunEvent(0, makeProgressEvent("run_started", 0)),
          makeRunEvent(1, makeProgressEvent("run_completed", 1)),
        ],
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useLiveRunTrace("http://test", "run-1"));

    // First load lands a still-running log, which starts the poll.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // One interval later the poll re-reads and sees the terminal completion event.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_RUN_TRACE_POLL_INTERVAL_MS);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.state).toMatchObject({ status: "streaming", done: true });

    // The log is final — no further polls as more time passes.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_RUN_TRACE_POLL_INTERVAL_MS * 3);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the prior timeline when a background poll fails (stale-while-revalidate)", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [makeRunEvent(0, makeProgressEvent("run_started", 0))],
      })
      .mockResolvedValueOnce({ ok: false, status: 503 });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useLiveRunTrace("http://test", "run-1"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.state.status).toBe("streaming");

    // A failed background refresh keeps the streamed timeline rather than blanking it to an error.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_RUN_TRACE_POLL_INTERVAL_MS);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const state = result.current.state;
    if (state.status !== "streaming") throw new Error("expected streaming");
    expect(state.events).toHaveLength(1);
  });

  it("surfaces a recoverable error when the very first load fails", async () => {
    stubFetch({ ok: false, status: 503 });

    const { result } = renderHook(() => useLiveRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("error"));
  });

  it("resolves to a done, empty stream without fetching when there is no runId", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const { result } = renderHook(() => useLiveRunTrace("http://test", undefined));

    await waitFor(() =>
      expect(result.current.state).toMatchObject({ status: "streaming", done: true }),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
