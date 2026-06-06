import { renderHook } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAutoHideScroll } from "./useAutoHideScroll";

describe("useAutoHideScroll", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("marks the element active while scrolling and clears it after the idle delay", () => {
    const element = document.createElement("div");
    const ref = { current: element };

    renderHook(() => useAutoHideScroll(ref, 800));

    // A scroll lights the scrollbar up.
    act(() => element.dispatchEvent(new Event("scroll")));
    expect(element.dataset.scrollActive).toBe("true");

    // It stays lit while scrolling continues within the idle window…
    act(() => {
      vi.advanceTimersByTime(500);
      element.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(500);
    });
    expect(element.dataset.scrollActive).toBe("true");

    // …then fades out once idle past the delay.
    act(() => vi.advanceTimersByTime(800));
    expect(element.dataset.scrollActive).toBeUndefined();
  });

  it("detaches the listener and clears the flag on unmount", () => {
    const element = document.createElement("div");
    const ref = { current: element };
    const { unmount } = renderHook(() => useAutoHideScroll(ref, 800));

    act(() => element.dispatchEvent(new Event("scroll")));
    expect(element.dataset.scrollActive).toBe("true");

    unmount();
    expect(element.dataset.scrollActive).toBeUndefined();
    // A post-unmount scroll is ignored (listener removed).
    act(() => element.dispatchEvent(new Event("scroll")));
    expect(element.dataset.scrollActive).toBeUndefined();
  });
});
