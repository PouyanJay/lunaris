import { renderHook } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useKeylessReadiness } from "./useKeylessReadiness";

vi.mock("../lib/keylessReadiness", () => ({ fetchKeylessReadiness: vi.fn() }));
import { fetchKeylessReadiness } from "../lib/keylessReadiness";

const mockFetch = vi.mocked(fetchKeylessReadiness);

// Flush the awaited probe + any rescheduled timer deterministically (no wall-clock waits).
async function tick(ms = 0): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useKeylessReadiness", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("does not probe while disabled", async () => {
    const { result } = renderHook(() => useKeylessReadiness("http://api", false));
    await tick();

    expect(result.current).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("keeps polling while the GPU is still provisioning", async () => {
    mockFetch.mockResolvedValue("provisioning");

    const { result } = renderHook(() => useKeylessReadiness("http://api", true));
    await tick();
    expect(result.current).toBe("provisioning");
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await tick(4000); // the poll interval elapses → it probes again (still unsettled)
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("stops polling once the status settles to ready", async () => {
    mockFetch.mockResolvedValue("ready");

    const { result } = renderHook(() => useKeylessReadiness("http://api", true));
    await tick();
    expect(result.current).toBe("ready");

    await tick(20000); // well past the interval → no further probe, the loop ended
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("stops probing and resets when it becomes disabled", async () => {
    mockFetch.mockResolvedValue("provisioning");

    const { result, rerender } = renderHook(
      ({ enabled }) => useKeylessReadiness("http://api", enabled),
      { initialProps: { enabled: true } },
    );
    await tick();
    expect(result.current).toBe("provisioning");

    rerender({ enabled: false });
    await tick();
    expect(result.current).toBeNull(); // cleared when the build is no longer active
  });
});
