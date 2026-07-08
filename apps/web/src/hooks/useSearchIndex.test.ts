import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse } from "../test/fixtures";
import { useSearchIndex } from "./useSearchIndex";

const SUMMARIES = [
  { id: "course-test", topic: "How binary search works" },
  { id: "course-dead", topic: "A course whose payload is gone" },
];

function studioFetch(options: { deadPayload?: boolean; summariesDown?: boolean } = {}) {
  return vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = input instanceof Request ? input.url : String(input);
    if (/\/api\/courses$/.test(url)) {
      if (options.summariesDown) return Promise.reject(new Error("down"));
      return Promise.resolve({ ok: true, json: async () => SUMMARIES });
    }
    if (url.includes("/api/courses/course-test")) {
      return Promise.resolve({ ok: true, json: async () => makeCourse() });
    }
    // course-dead's full payload fails.
    return Promise.reject(new Error("payload gone"));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("useSearchIndex", () => {
  it("stays idle and fetches nothing until first activated", () => {
    const fetchMock = studioFetch();
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useSearchIndex("http://test", false));

    expect(result.current.status).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a failed course payload still contributes its course row (partial truth)", async () => {
    vi.stubGlobal("fetch", studioFetch({ deadPayload: true }));

    const { result } = renderHook(() => useSearchIndex("http://test", true));
    await waitFor(() => expect(result.current.status).toBe("ready"));

    const entries = result.current.status === "ready" ? result.current.entries : [];
    const labels = entries.map((entry) => entry.label);
    // Both course rows survive; only the healthy course contributes lessons/concepts.
    expect(labels).toContain("How binary search works");
    expect(labels).toContain("A course whose payload is gone");
    expect(
      entries.some((entry) => entry.kind === "lesson" && entry.courseId === "course-test"),
    ).toBe(true);
    expect(
      entries.some((entry) => entry.kind !== "course" && entry.courseId === "course-dead"),
    ).toBe(false);
  });

  it("keeps the session cache across close/reopen — one build, not one per open", async () => {
    const fetchMock = studioFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { result, rerender } = renderHook(({ active }) => useSearchIndex("http://test", active), {
      initialProps: { active: true },
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    const callsAfterBuild = fetchMock.mock.calls.length;

    // Act — close and reopen the palette.
    rerender({ active: false });
    rerender({ active: true });

    // Assert
    expect(fetchMock.mock.calls.length).toBe(callsAfterBuild);
    expect(result.current.status).toBe("ready");
  });

  it("a summaries failure is an error state that a reopen can retry", async () => {
    const fetchMock = studioFetch({ summariesDown: true });
    vi.stubGlobal("fetch", fetchMock);
    const { result, rerender } = renderHook(({ active }) => useSearchIndex("http://test", active), {
      initialProps: { active: true },
    });
    await waitFor(() => expect(result.current.status).toBe("error"));

    // Act — the backend recovers; the next open rebuilds.
    vi.stubGlobal("fetch", studioFetch());
    rerender({ active: false });
    rerender({ active: true });

    // Assert
    await waitFor(() => expect(result.current.status).toBe("ready"));
  });
});
