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

/** A fetch double that serves the empty snapshot on GET and routes every progress PUT through
 *  `onPut` — resolve (default) for the happy paths, reject for the reconciliation paths. */
function snapshotFetch(
  onPut: () => Promise<unknown> = () => Promise.resolve({ ok: true, status: 204 }),
) {
  return vi.fn((_input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "PUT") return onPut();
    return Promise.resolve({
      ok: true,
      json: async () => ({ courseId: "c1", objectives: [], lessons: [] }),
    });
  });
}

describe("useCourseProgress — markOpened", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("records the course open with the lesson position", async () => {
    // Arrange
    const fetchMock = snapshotFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));

    // Act
    act(() => result.current.markOpened("m1-l0"));

    // Assert

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "PUT",
      );
      expect(put?.[0]).toBe("http://test/api/courses/c1/progress/opened");
      expect(JSON.parse(String(put?.[1]?.body))).toEqual({ lastLessonId: "m1-l0" });
    });
  });

  it("a bare touch sends no position, so the server preserves the recorded one", async () => {
    const fetchMock = snapshotFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));

    act(() => result.current.markOpened());

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "PUT",
      );
      expect(JSON.parse(String(put?.[1]?.body))).toEqual({});
    });
  });

  it("is disabled on the offline surface (empty apiBaseUrl)", () => {
    const fetchMock = snapshotFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("", "c1"));

    act(() => result.current.markOpened("m1-l0"));

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useCourseProgress — write reconciliation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rolls back an optimistic objective mark by refetching when the PUT fails", async () => {
    // Arrange — GET always serves an empty snapshot; the PUT rejects.
    const fetchMock = snapshotFetch(() => Promise.reject(new Error("down")));
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
    const fetchMock = snapshotFetch(() => Promise.reject(new Error("down")));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCourseProgress("http://test", "c1"));
    await waitFor(() => expect(result.current.progress).not.toBeNull());

    act(() => result.current.markLesson("m-1-l0", "done"));
    expect(result.current.progress?.lessons).toHaveLength(1);

    await waitFor(() => expect(result.current.progress?.lessons).toHaveLength(0));
  });
});
