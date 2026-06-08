import { afterEach, describe, expect, it, vi } from "vitest";

// Auth not configured: no Supabase client. Separate file because vi.mock is hoisted per-file.
vi.mock("./supabase", () => ({ supabase: null, getAccessToken: vi.fn() }));

import { authedFetch } from "./apiClient";

describe("authedFetch (auth unconfigured)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("delegates straight to fetch with the original init (no auth indirection)", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok"));
    const init = { method: "GET" };

    // Act
    await authedFetch("http://api/x", init);

    // Assert — same args as a bare fetch; no headers added, no token resolution
    expect(fetchSpy).toHaveBeenCalledWith("http://api/x", init);
  });
});
