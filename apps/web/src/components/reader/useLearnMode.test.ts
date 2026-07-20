import { describe, expect, it } from "vitest";

import { deriveEffectiveMode } from "./useLearnMode";

describe("deriveEffectiveMode", () => {
  it("opens in Watch by default when a chaptered video exists and no choice was made", () => {
    expect(deriveEffectiveMode(null, true)).toBe("watch");
  });

  it("opens in Learn by default when no video exists", () => {
    expect(deriveEffectiveMode(null, false)).toBe("learn");
  });

  it("honours an explicit Read choice, video or not", () => {
    expect(deriveEffectiveMode("read", true)).toBe("read");
    expect(deriveEffectiveMode("read", false)).toBe("read");
  });

  it("honours an explicit Learn choice even when a video exists", () => {
    expect(deriveEffectiveMode("learn", true)).toBe("learn");
  });

  it("shows Watch for a stored Watch preference when a video exists", () => {
    expect(deriveEffectiveMode("watch", true)).toBe("watch");
  });

  it("clamps a stored Watch preference to Learn when no video exists", () => {
    expect(deriveEffectiveMode("watch", false)).toBe("learn");
  });
});
