import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the transport so the hook's caching/SWR behaviour is what's under test, not the network.
vi.mock("../lib/library", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/library")>();
  return { ...actual, fetchCourseSummaries: vi.fn() };
});
import { fetchCourseSummaries, LibraryError } from "../lib/library";
import { clearLibraryCache } from "./libraryCache";
import { useLibrary } from "./useLibrary";
import { makeCourseSummary } from "../test/fixtures";

const fetchSummaries = vi.mocked(fetchCourseSummaries);
const API = "http://api.test";
const ONE = [makeCourseSummary({ id: "c1", topic: "How HTTPS works" })];

beforeEach(() => {
  clearLibraryCache(); // the module cache survives across tests — reset it
  fetchSummaries.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("useLibrary cross-navigation cache", () => {
  it("cold load: loading, then ready with the loaded courses", async () => {
    fetchSummaries.mockResolvedValueOnce(ONE);
    const { result } = renderHook(() => useLibrary(API));

    expect(result.current.state).toEqual({ status: "loading" });
    await waitFor(() => expect(result.current.state).toEqual({ status: "ready", courses: ONE }));
  });

  it("re-entry paints the cached grid instantly (no skeleton flash) and revalidates", async () => {
    fetchSummaries.mockResolvedValue(ONE);
    const first = renderHook(() => useLibrary(API));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    first.unmount();
    fetchSummaries.mockClear();

    // Remount — as when the user navigates away from My-courses and back.
    const second = renderHook(() => useLibrary(API));

    // No loading flash: the exact cached grid is shown immediately...
    expect(second.result.current.state).toEqual({ status: "ready", courses: ONE });
    // ...and the grid still revalidates quietly in the background, settling on the fresh data.
    expect(fetchSummaries).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(second.result.current.state).toEqual({ status: "ready", courses: ONE }),
    );
  });

  it("clearLibraryCache (an account switch) forces a cold load again", async () => {
    fetchSummaries.mockResolvedValue(ONE);
    const first = renderHook(() => useLibrary(API));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    first.unmount();

    clearLibraryCache();
    const second = renderHook(() => useLibrary(API));

    // The next account starts from the skeleton, never the previous user's cached grid...
    expect(second.result.current.state).toEqual({ status: "loading" });
    // ...then loads its own library (awaited so no state update dangles past the test).
    await waitFor(() => expect(second.result.current.state).toEqual({ status: "ready", courses: ONE }));
  });

  it("keeps the cached cards when a background revalidation fails", async () => {
    fetchSummaries.mockResolvedValueOnce(ONE);
    const first = renderHook(() => useLibrary(API));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    first.unmount();

    fetchSummaries.mockRejectedValueOnce(new LibraryError("backend down"));
    const second = renderHook(() => useLibrary(API));

    // Shown from cache immediately, and a failed refresh does NOT blank it to an error.
    expect(second.result.current.state.status).toBe("ready");
    await waitFor(() => expect(fetchSummaries).toHaveBeenCalled());
    expect(second.result.current.state.status).toBe("ready");
  });
});
