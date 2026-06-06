import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RAIL_DEFAULT_WIDTH, RAIL_MAX_WIDTH, RAIL_MIN_WIDTH, useRailLayout } from "./useRailLayout";

/** Build a minimal keyboard event for the width nudger; only `key` and `preventDefault` matter. */
function keyEvent(key: string) {
  return { key, preventDefault: () => {} } as React.KeyboardEvent;
}

// localStorage is reset after every test by the shared setup, so each test starts from defaults.
describe("useRailLayout", () => {
  it("starts expanded at the default width", () => {
    const { result } = renderHook(() => useRailLayout());

    expect(result.current.collapsed).toBe(false);
    expect(result.current.width).toBe(RAIL_DEFAULT_WIDTH);
    expect(result.current.resizing).toBe(false);
  });

  it("toggles collapsed and persists it across remounts", () => {
    const { result, unmount } = renderHook(() => useRailLayout());

    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);

    unmount();
    const { result: remounted } = renderHook(() => useRailLayout());
    expect(remounted.current.collapsed).toBe(true);
  });

  it("widens with ArrowLeft and narrows with ArrowRight (the rail sits on the right)", () => {
    const { result, unmount } = renderHook(() => useRailLayout());

    act(() => result.current.nudgeWidth(keyEvent("ArrowLeft")));
    const wider = result.current.width;
    expect(wider).toBeGreaterThan(RAIL_DEFAULT_WIDTH);

    act(() => result.current.nudgeWidth(keyEvent("ArrowRight")));
    expect(result.current.width).toBe(RAIL_DEFAULT_WIDTH);

    // Width survives a remount (persisted).
    act(() => result.current.nudgeWidth(keyEvent("ArrowLeft")));
    unmount();
    const { result: remounted } = renderHook(() => useRailLayout());
    expect(remounted.current.width).toBe(wider);
  });

  it("jumps to the bounds with Home/End and clamps there", () => {
    const { result } = renderHook(() => useRailLayout());

    act(() => result.current.nudgeWidth(keyEvent("End")));
    expect(result.current.width).toBe(RAIL_MAX_WIDTH);
    act(() => result.current.nudgeWidth(keyEvent("ArrowLeft")));
    expect(result.current.width).toBe(RAIL_MAX_WIDTH);

    act(() => result.current.nudgeWidth(keyEvent("Home")));
    expect(result.current.width).toBe(RAIL_MIN_WIDTH);
    act(() => result.current.nudgeWidth(keyEvent("ArrowRight")));
    expect(result.current.width).toBe(RAIL_MIN_WIDTH);
  });

  it("ignores keys other than the resize controls", () => {
    const { result } = renderHook(() => useRailLayout());

    act(() => result.current.nudgeWidth(keyEvent("Enter")));

    expect(result.current.width).toBe(RAIL_DEFAULT_WIDTH);
  });
});
