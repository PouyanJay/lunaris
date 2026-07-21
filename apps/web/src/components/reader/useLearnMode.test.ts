import { describe, expect, it } from "vitest";

import { deriveEffectiveMode } from "./useLearnMode";

// Signature: deriveEffectiveMode(preference, watchAvailable, watchOffered). `watchOffered` is Watch
// being available at all (an online reader); `watchAvailable` is a ready chaptered video existing —
// the front-door trigger. Only Learn and Watch remain (Read is retired).
describe("deriveEffectiveMode", () => {
  it("opens in Watch by default when a chaptered video exists and no choice was made", () => {
    expect(deriveEffectiveMode(null, true, true)).toBe("watch");
  });

  it("opens in Learn by default when no ready video exists", () => {
    expect(deriveEffectiveMode(null, false, true)).toBe("learn");
  });

  it("honours an explicit Learn choice even when a video exists", () => {
    expect(deriveEffectiveMode("learn", true, true)).toBe("learn");
  });

  it("shows Watch for a stored Watch preference when a ready video exists", () => {
    expect(deriveEffectiveMode("watch", true, true)).toBe("watch");
  });

  it("keeps a stored Watch preference on a video-less lesson (Watch shows the generate CTA)", () => {
    expect(deriveEffectiveMode("watch", false, true)).toBe("watch");
  });

  it("falls back to Learn whenever Watch is not offered (offline), whatever the preference", () => {
    expect(deriveEffectiveMode("watch", true, false)).toBe("learn");
    expect(deriveEffectiveMode(null, true, false)).toBe("learn");
  });
});
