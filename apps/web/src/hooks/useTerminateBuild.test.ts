import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useTerminateBuild } from "./useTerminateBuild";

describe("useTerminateBuild", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cancels server-side BEFORE resetting the local stream, then refreshes", async () => {
    // Record call order so we can prove cancel precedes reset (so the run lands CANCELLED, not the
    // disconnect→FAILED path). The cancel POST resolves 202.
    const order: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        order.push("cancel");
        return Promise.resolve({ ok: true, status: 202 });
      }),
    );
    const reset = vi.fn(() => order.push("reset"));
    const reload = vi.fn(() => order.push("reload"));
    const { result } = renderHook(() => useTerminateBuild("http://test", reset, reload));

    act(() => result.current.request("run-1"));
    act(() => void result.current.confirm());

    await waitFor(() => expect(result.current.isConfirming).toBe(false));
    expect(order).toEqual(["cancel", "reset", "reload"]);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-1/cancel"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("keeps the dialog open with the reason when the cancel fails (build still running)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    const reset = vi.fn();
    const { result } = renderHook(() => useTerminateBuild("http://test", reset, vi.fn()));

    act(() => result.current.request("run-1"));
    act(() => void result.current.confirm());

    await waitFor(() => expect(result.current.terminateError).not.toBeNull());
    expect(result.current.isConfirming).toBe(true); // dialog stays open
    expect(reset).not.toHaveBeenCalled(); // the local stream is NOT stopped on a real failure
  });

  it("treats a 404 (already finished) as done — stops locally without an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const reset = vi.fn();
    const { result } = renderHook(() => useTerminateBuild("http://test", reset, vi.fn()));

    act(() => result.current.request("run-1"));
    act(() => void result.current.confirm());

    await waitFor(() => expect(result.current.isConfirming).toBe(false));
    expect(result.current.terminateError).toBeNull();
    expect(reset).toHaveBeenCalledOnce();
  });

  it("skips the cancel call when there's no run_id but still stops locally", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const reset = vi.fn();
    const { result } = renderHook(() => useTerminateBuild("http://test", reset, vi.fn()));

    act(() => result.current.request(undefined));
    act(() => void result.current.confirm());

    await waitFor(() => expect(reset).toHaveBeenCalledOnce());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
