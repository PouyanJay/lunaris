import { afterEach, describe, expect, it, vi } from "vitest";

import { isLiveEnabled } from "./product";
import { resolveProductRoute } from "./routes";

describe("resolveProductRoute", () => {
  it.each([
    ["/live", "live"],
    ["/live/", "live"],
    ["/live/session/abc", "live"],
    ["/", "studio"],
    ["/courses/abc", "studio"],
    ["/settings", "studio"],
    // A path that merely starts with the same letters is Studio's, not Live's — the boundary is a
    // path segment, not a prefix.
    ["/livestream", "studio"],
    ["/liveness", "studio"],
  ])("routes %s to %s", (pathname, kind) => {
    expect(resolveProductRoute(pathname)).toBe(kind);
  });
});

describe("isLiveEnabled — the default-off flag", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("is off when the flag is unset — the production default", () => {
    expect(isLiveEnabled()).toBe(false);
  });

  it('is on only for an exact "true"', () => {
    vi.stubEnv("VITE_LIVE_ENABLED", "true");
    expect(isLiveEnabled()).toBe(true);
  });

  it.each([["false"], ["1"], ["yes"], ["TRUE"], [""]])(
    "stays off for the ambiguous value %s",
    (value) => {
      vi.stubEnv("VITE_LIVE_ENABLED", value);
      expect(isLiveEnabled()).toBe(false);
    },
  );
});
