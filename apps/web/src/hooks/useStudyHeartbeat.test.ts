import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStudyHeartbeat } from "./useStudyHeartbeat";

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useStudyHeartbeat", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility("visible");
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setVisibility("visible");
  });

  it("beats on mount and then once per minute while visible", () => {
    // Arrange
    const fetchMock = vi.fn((_input: RequestInfo | URL) =>
      Promise.resolve({ ok: true, status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    // Act
    renderHook(() => useStudyHeartbeat("http://test", true));
    vi.advanceTimersByTime(60_000);
    vi.advanceTimersByTime(60_000);

    // Assert — mount beat + two interval beats, all at the heartbeat endpoint.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/api/activity/heartbeat");
  });

  it("pauses while the document is hidden and resumes on return", () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useStudyHeartbeat("http://test", true));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Act — tab goes to the background: study minutes must not accrue.
    setVisibility("hidden");
    vi.advanceTimersByTime(180_000);
    const whileHidden = fetchMock.mock.calls.length;

    // Return to the tab: an immediate beat, then the cadence resumes.
    setVisibility("visible");
    vi.advanceTimersByTime(60_000);

    // Assert
    expect(whileHidden).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does nothing when inactive or offline", () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    // Act
    renderHook(() => useStudyHeartbeat("", true));
    renderHook(() => useStudyHeartbeat("http://test", false));
    vi.advanceTimersByTime(120_000);

    // Assert
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stops beating after unmount", () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderHook(() => useStudyHeartbeat("http://test", true));

    // Act
    unmount();
    vi.advanceTimersByTime(180_000);

    // Assert — only the mount beat.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("swallows transport failures — telemetry never breaks the reader", async () => {
    // Arrange
    const fetchMock = vi.fn(() => Promise.reject(new Error("network down")));
    vi.stubGlobal("fetch", fetchMock);

    // Act — a failing beat must not surface as an unhandled rejection.
    renderHook(() => useStudyHeartbeat("http://test", true));
    await vi.advanceTimersByTimeAsync(60_000);

    // Assert
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
