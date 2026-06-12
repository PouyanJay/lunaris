import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useBeforeUnloadGuard } from "./useBeforeUnloadGuard";

function fireBeforeUnload(): Event {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
}

describe("useBeforeUnloadGuard", () => {
  it("asks the browser to confirm leaving while active", () => {
    // Arrange — a device build in flight: closing the tab would kill it.
    renderHook(() => useBeforeUnloadGuard(true));

    // Act
    const event = fireBeforeUnload();

    // Assert — the unload is intercepted. (The hook also sets the legacy returnValue="" leg
    // for engines that key off it, but jsdom's plain Event exposes returnValue as the legacy
    // boolean inverse of defaultPrevented, so only the modern leg is observable here.)
    expect(event.defaultPrevented).toBe(true);
  });

  it("lets the tab close freely while inactive", () => {
    // Arrange — a server build (or no build): closing the tab costs nothing.
    renderHook(() => useBeforeUnloadGuard(false));

    // Act
    const event = fireBeforeUnload();

    // Assert
    expect(event.defaultPrevented).toBe(false);
  });

  it("releases the guard when the consumer unmounts", () => {
    // Arrange
    const { unmount } = renderHook(() => useBeforeUnloadGuard(true));

    // Act
    unmount();
    const event = fireBeforeUnload();

    // Assert — no leaked listener keeps blocking navigation.
    expect(event.defaultPrevented).toBe(false);
  });
});
