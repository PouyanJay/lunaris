import { afterEach, describe, expect, it, vi } from "vitest";

// Simulate auth being configured (a truthy client) with a controllable token resolver.
const { getAccessTokenMock } = vi.hoisted(() => ({ getAccessTokenMock: vi.fn() }));
vi.mock("./supabase", () => ({ supabase: {}, getAccessToken: getAccessTokenMock }));

import { authedFetch } from "./apiClient";

describe("authedFetch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("attaches the bearer token and preserves the request init when signed in", async () => {
    // Arrange
    getAccessTokenMock.mockResolvedValue("tok-123");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok"));

    // Act
    await authedFetch("http://api/x", { method: "POST" });

    // Assert
    const init = fetchSpy.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok-123");
    expect(init?.method).toBe("POST");
  });

  it("sends no Authorization header when not signed in", async () => {
    // Arrange
    getAccessTokenMock.mockResolvedValue(null);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok"));

    // Act
    await authedFetch("http://api/x");

    // Assert
    const init = fetchSpy.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Authorization")).toBeNull();
  });
});
