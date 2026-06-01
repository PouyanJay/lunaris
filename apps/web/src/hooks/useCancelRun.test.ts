import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCancelRun } from "./useCancelRun";

describe("useCancelRun", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cancels by run_id, marks it pending, then refreshes the history", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 202 }));
    const reload = vi.fn();
    const { result } = renderHook(() => useCancelRun("http://test", reload));

    act(() => result.current.cancel("run-1"));
    expect(result.current.cancellingRunId).toBe("run-1");

    await waitFor(() => expect(result.current.cancellingRunId).toBeNull());
    expect(reload).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-1/cancel"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("swallows a failed cancel and still refreshes (the reload reconciles the true status)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const reload = vi.fn();
    const { result } = renderHook(() => useCancelRun("http://test", reload));

    act(() => result.current.cancel("run-1"));

    await waitFor(() => expect(result.current.cancellingRunId).toBeNull());
    expect(reload).toHaveBeenCalledOnce();
  });

  it("is a no-op without a run_id", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const reload = vi.fn();
    const { result } = renderHook(() => useCancelRun("http://test", reload));

    act(() => result.current.cancel(undefined));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    expect(result.current.cancellingRunId).toBeNull();
  });
});
