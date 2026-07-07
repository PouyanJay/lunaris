import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCourseProgress } from "./useCourseProgress";

describe("useCourseProgress", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the caller's progress snapshot for a course", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          courseId: "c1",
          objectives: [{ moduleId: "m1", objectiveIndex: 0, understoodAt: "2026-07-07T00:00:00Z" }],
          lessons: [{ lessonId: "m1-l0", state: "in_progress", updatedAt: "2026-07-07T00:00:00Z" }],
        }),
      }),
    );

    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));

    await waitFor(() => expect(result.current.progress).not.toBeNull());
    expect(result.current.progress?.objectives).toHaveLength(1);
    expect(result.current.progress?.lessons[0]?.lessonId).toBe("m1-l0");
  });

  it("stays empty (null) when the fetch fails — progress is best-effort", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("down"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current.progress).toBeNull();
  });
});

describe("useCourseProgress — write reconciliation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rolls back an optimistic objective mark by refetching when the PUT fails", async () => {
    // Arrange — GET always serves an empty snapshot; the PUT rejects.
    const fetchMock = vi.fn((_input: Parameters<typeof fetch>[0], init?: RequestInit) => {      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "PUT") return Promise.reject(new Error("down"));
      return Promise.resolve({
        ok: true,
        json: async () => ({ courseId: "c1", objectives: [], lessons: [] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));
    await waitFor(() => expect(result.current.progress).not.toBeNull());

    // Act — optimistic mark, then the failed PUT triggers the reconcile refetch.
    act(() => result.current.markObjective("m-1", 0, true));
    expect(result.current.progress?.objectives).toHaveLength(1);

    // Assert — the refetched (server) truth wins: the optimistic mark is gone.
    await waitFor(() => expect(result.current.progress?.objectives).toHaveLength(0));
  });

  it("rolls back an optimistic lesson mark by refetching when the PUT fails", async () => {
    const fetchMock = vi.fn((_input: Parameters<typeof fetch>[0], init?: RequestInit) => {      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "PUT") return Promise.reject(new Error("down"));
      return Promise.resolve({
        ok: true,
        json: async () => ({ courseId: "c1", objectives: [], lessons: [] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));
    await waitFor(() => expect(result.current.progress).not.toBeNull());

    act(() => result.current.markLesson("m-1-l0", "done"));
    expect(result.current.progress?.lessons).toHaveLength(1);

    await waitFor(() => expect(result.current.progress?.lessons).toHaveLength(0));
  });
});
