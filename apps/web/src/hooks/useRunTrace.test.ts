import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeAgentEvent, makeProgressEvent, makeRunEvent } from "../test/fixtures";
import { useRunTrace } from "./useRunTrace";

function stubFetch(value: { ok: boolean; status?: number; json?: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, ...value }));
}

describe("useRunTrace", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads a run's log and splits it into the two timeline streams", async () => {
    const rows = [
      makeRunEvent(0, makeProgressEvent("run_started", 0)),
      makeRunEvent(1, makeAgentEvent("reasoning", 0, { text: "Planning…" })),
      makeRunEvent(2, makeProgressEvent("concepts_extracted", 1)),
    ];
    stubFetch({ ok: true, json: async () => rows });

    const { result } = renderHook(() => useRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    const state = result.current.state;
    if (state.status !== "ready") throw new Error("expected ready");
    expect(state.events).toHaveLength(2);
    expect(state.agentEvents).toHaveLength(1);
  });

  it("resolves to empty when the run left no build record", async () => {
    stubFetch({ ok: true, json: async () => [] });

    const { result } = renderHook(() => useRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("empty"));
  });

  it("resolves to empty without fetching when there is no runId", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const { result } = renderHook(() => useRunTrace("http://test", undefined));

    await waitFor(() => expect(result.current.state.status).toBe("empty"));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("surfaces a recoverable error on an HTTP failure", async () => {
    stubFetch({ ok: false, status: 503 });

    const { result } = renderHook(() => useRunTrace("http://test", "run-1"));

    await waitFor(() => expect(result.current.state.status).toBe("error"));
    const state = result.current.state;
    if (state.status !== "error") throw new Error("expected error");
    expect(state.message).toMatch(/build record/i);
  });

  it("discards a superseded load's late result", async () => {
    let resolveFirst!: (value: unknown) => void;
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    const { result, rerender } = renderHook(({ id }) => useRunTrace("http://test", id), {
      initialProps: { id: "run-1" },
    });
    expect(result.current.state.status).toBe("loading");

    // A new runId starts a second load and aborts the first.
    rerender({ id: "run-2" });
    await waitFor(() => expect(result.current.state.status).toBe("empty"));

    // The first (aborted) fetch resolving late must NOT overwrite the second load's result —
    // if the abort guard were removed, this would flip the state back to "ready".
    resolveFirst({
      ok: true,
      json: async () => [makeRunEvent(0, makeProgressEvent("run_started", 0))],
    });
    await Promise.resolve();
    expect(result.current.state.status).toBe("empty");
  });
});
