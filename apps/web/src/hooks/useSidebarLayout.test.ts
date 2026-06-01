import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  useSidebarLayout,
} from "./useSidebarLayout";

/** Build a minimal keyboard event for the width nudger; only `key` and `preventDefault` matter. */
function keyEvent(key: string) {
  return { key, preventDefault: () => {} } as React.KeyboardEvent;
}

// localStorage is reset after every test by the shared setup, so each test starts from defaults.
describe("useSidebarLayout", () => {
  it("starts expanded at the default width", () => {
    const { result } = renderHook(() => useSidebarLayout());

    expect(result.current.collapsed).toBe(false);
    expect(result.current.width).toBe(SIDEBAR_DEFAULT_WIDTH);
    expect(result.current.resizing).toBe(false);
  });

  it("toggles collapsed and persists it across remounts", () => {
    const { result, unmount } = renderHook(() => useSidebarLayout());

    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);

    // A fresh mount restores the persisted collapse preference.
    unmount();
    const { result: remounted } = renderHook(() => useSidebarLayout());
    expect(remounted.current.collapsed).toBe(true);
  });

  it("nudges the width with the arrow keys and persists it", () => {
    const { result, unmount } = renderHook(() => useSidebarLayout());

    act(() => result.current.nudgeWidth(keyEvent("ArrowRight")));
    const wider = result.current.width;
    expect(wider).toBeGreaterThan(SIDEBAR_DEFAULT_WIDTH);

    act(() => result.current.nudgeWidth(keyEvent("ArrowLeft")));
    expect(result.current.width).toBe(SIDEBAR_DEFAULT_WIDTH);

    act(() => result.current.nudgeWidth(keyEvent("ArrowRight")));
    unmount();
    const { result: remounted } = renderHook(() => useSidebarLayout());
    expect(remounted.current.width).toBe(wider);
  });

  it("jumps to the bounds with Home/End and clamps the arrow keys there", () => {
    const { result } = renderHook(() => useSidebarLayout());

    // End jumps to the maximum, and a further widen can't exceed it.
    act(() => result.current.nudgeWidth(keyEvent("End")));
    expect(result.current.width).toBe(SIDEBAR_MAX_WIDTH);
    act(() => result.current.nudgeWidth(keyEvent("ArrowRight")));
    expect(result.current.width).toBe(SIDEBAR_MAX_WIDTH);

    // Home jumps to the minimum, and a further narrow can't go below it.
    act(() => result.current.nudgeWidth(keyEvent("Home")));
    expect(result.current.width).toBe(SIDEBAR_MIN_WIDTH);
    act(() => result.current.nudgeWidth(keyEvent("ArrowLeft")));
    expect(result.current.width).toBe(SIDEBAR_MIN_WIDTH);
  });

  it("ignores keys other than the resize controls", () => {
    const { result } = renderHook(() => useSidebarLayout());

    act(() => result.current.nudgeWidth(keyEvent("Enter")));

    expect(result.current.width).toBe(SIDEBAR_DEFAULT_WIDTH);
  });
});
