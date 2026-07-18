import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/library", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/library")>();
  return { ...actual, fetchCourseSummaries: vi.fn() };
});
import { fetchCourseSummaries } from "../lib/library";
import { clearLibraryCache, getLibraryCache, setLibraryCache } from "./libraryCache";
import { prefetchLibrary } from "./prefetchLibrary";
import { makeCourseSummary } from "../test/fixtures";

const fetchSummaries = vi.mocked(fetchCourseSummaries);
const API = "http://api.test";
const ONE = [makeCourseSummary({ id: "c1" })];

beforeEach(() => {
  clearLibraryCache();
  fetchSummaries.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("prefetchLibrary", () => {
  it("warms the cache so the click lands on ready data", async () => {
    fetchSummaries.mockResolvedValueOnce(ONE);

    prefetchLibrary(API);

    await waitFor(() => expect(getLibraryCache()).toEqual(ONE));
    expect(fetchSummaries).toHaveBeenCalledOnce();
  });

  it("does nothing when the grid is already cached", () => {
    setLibraryCache(ONE);

    prefetchLibrary(API);

    expect(fetchSummaries).not.toHaveBeenCalled();
  });

  it("coalesces repeated hovers into a single request", async () => {
    let resolve: (courses: typeof ONE) => void = () => {};
    fetchSummaries.mockReturnValueOnce(new Promise((r) => (resolve = r)));

    prefetchLibrary(API);
    prefetchLibrary(API); // a lingering hover / re-enter must not fire a second request

    expect(fetchSummaries).toHaveBeenCalledOnce();
    resolve(ONE);
    await waitFor(() => expect(getLibraryCache()).toEqual(ONE));
  });

  it("leaves the cache cold when the prefetch fails (the real load owns the error)", async () => {
    fetchSummaries.mockRejectedValueOnce(new Error("network"));

    prefetchLibrary(API);

    await waitFor(() => expect(fetchSummaries).toHaveBeenCalled());
    expect(getLibraryCache()).toBeNull();
  });
});
