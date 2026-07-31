import type { User } from "@supabase/supabase-js";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isLiveEnabled, resolveLastProduct, type Product } from "./product";
import { productEnteredAt, resolveProductRoute } from "./routes";

function userWith(metadata: unknown): User {
  return { user_metadata: metadata } as unknown as User;
}

describe("resolveLastProduct — the fail-open contract", () => {
  it.each<[string, Product]>([
    ["studio", "studio"],
    ["live", "live"],
  ])("reads a valid remembered product (%s)", (stored, expected) => {
    expect(resolveLastProduct(userWith({ last_product: stored }))).toBe(expected);
  });

  // Every one of these must land on "no preference", which sends the user to the gateway — a real
  // choice. The failure mode this guards against is a blank screen or a redirect loop.
  it.each([
    ["a missing key", {}],
    ["an unknown product", { last_product: "workshop" }],
    ["the wrong case", { last_product: "Live" }],
    ["surrounding whitespace", { last_product: " live " }],
    ["an empty string", { last_product: "" }],
    ["a number", { last_product: 2 }],
    ["a boolean", { last_product: true }],
    ["null", { last_product: null }],
    ["an object", { last_product: { name: "live" } }],
    ["an array", { last_product: ["live"] }],
    ["absent metadata", undefined],
  ])("falls open to no preference for %s", (_case, metadata) => {
    expect(resolveLastProduct(userWith(metadata))).toBeNull();
  });

  it("falls open when there is no user at all", () => {
    expect(resolveLastProduct(null)).toBeNull();
  });
});

describe("resolveProductRoute", () => {
  it.each([
    ["/live", "live"],
    ["/live/", "live"],
    ["/live/session/abc", "live"],
    ["/gateway", "gateway"],
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

describe("productEnteredAt", () => {
  it.each([
    ["/live", "live"],
    ["/live/session/abc", "live"],
    ["/courses/abc", "studio"],
    ["/settings", "studio"],
  ])("treats %s as entering %s", (pathname, product) => {
    expect(productEnteredAt(pathname)).toBe(product);
  });

  it.each([["/"], ["/gateway"]])(
    "treats %s as ambiguous, so arriving there chooses nothing",
    (pathname) => {
      expect(productEnteredAt(pathname)).toBeNull();
    },
  );
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
