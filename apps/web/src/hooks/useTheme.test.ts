import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTheme } from "./useTheme";

// localStorage is reset globally after each test (see test/setup.ts); the data-theme attribute on
// <html> is this suite's own global state, so reset it before each test for order-independence.
beforeEach(() => document.documentElement.removeAttribute("data-theme"));
afterEach(() => vi.restoreAllMocks());

describe("useTheme", () => {
  it("defaults to light and applies it to the document", () => {
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("toggles to dark, applies it, and persists the choice", () => {
    const { result } = renderHook(() => useTheme());

    act(() => result.current.toggle());

    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("lunaris-theme")).toBe("dark");
  });

  it("toggles back to light after a second toggle", () => {
    const { result } = renderHook(() => useTheme());

    act(() => result.current.toggle());
    act(() => result.current.toggle());

    expect(result.current.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("adopts the theme the boot script already set on <html>", () => {
    // The no-flash script in index.html sets data-theme before React mounts; the hook mirrors it.
    document.documentElement.setAttribute("data-theme", "dark");

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("dark");
  });

  it("keeps the theme-color meta in sync (the browser-chrome colour)", () => {
    const meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    meta.setAttribute("content", "#ffffff");
    document.head.appendChild(meta);

    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle());

    expect(meta.getAttribute("content")).toBe("#090a0c");
    document.head.removeChild(meta);
  });

  it("still applies the theme when localStorage is unavailable (private mode)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });

    const { result } = renderHook(() => useTheme());

    // The swallowed storage error must not break the in-session theme.
    act(() => result.current.toggle());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
