import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeRun } from "../test/fixtures";
import { useOpenedRun } from "./useOpenedRun";

describe("useOpenedRun", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("starts closed", () => {
    const { result } = renderHook(() => useOpenedRun("http://test"));
    expect(result.current.state.status).toBe("closed");
  });

  it("opens a run's course by id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => makeCourse({ id: "c-1" }) }),
    );
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-1", topic: "queues" })));

    expect(result.current.state).toMatchObject({ status: "loading", courseId: "c-1" });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.state).toMatchObject({ status: "ready", courseId: "c-1" });
  });

  it("surfaces a recoverable error when the course is gone (404)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun({ id: "c-9", topic: "trees" })));

    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(result.current.state).toMatchObject({
      status: "error",
      courseId: "c-9",
      topic: "trees",
    });
  });

  it("closes back to the build surface", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => makeCourse() }));
    const { result } = renderHook(() => useOpenedRun("http://test"));

    act(() => result.current.open(makeRun()));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.close());

    expect(result.current.state.status).toBe("closed");
  });
});
