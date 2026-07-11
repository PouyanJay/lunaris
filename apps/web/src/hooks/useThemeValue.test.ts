import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useThemeValue } from "./useThemeValue";

afterEach(() => {
  // Unmount (disconnecting the MutationObserver) BEFORE mutating the attribute, so the observer
  // can't fire a state update outside act() — a same-level afterEach runs before RTL's auto-cleanup.
  cleanup();
  document.documentElement.removeAttribute("data-theme");
});

describe("useThemeValue", () => {
  it("reads the initial theme off <html data-theme> (default light)", () => {
    const { result } = renderHook(() => useThemeValue());
    expect(result.current).toBe("light");
  });

  it("reads dark when the attribute is already set", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    const { result } = renderHook(() => useThemeValue());
    expect(result.current).toBe("dark");
  });

  it("tracks a live theme change without owning it", async () => {
    const { result } = renderHook(() => useThemeValue());
    expect(result.current).toBe("light");

    act(() => document.documentElement.setAttribute("data-theme", "dark"));
    await waitFor(() => expect(result.current).toBe("dark"));

    act(() => document.documentElement.setAttribute("data-theme", "light"));
    await waitFor(() => expect(result.current).toBe("light"));
  });

  it("never writes the attribute itself (read-only observer)", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    renderHook(() => useThemeValue());
    // Observing must not flip or clear the attribute the shell owns.
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
