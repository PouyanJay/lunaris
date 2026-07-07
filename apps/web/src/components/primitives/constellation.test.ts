import { describe, expect, it } from "vitest";

import {
  buildConstellation,
  CANVAS_H,
  CANVAS_MARGIN_X,
  CANVAS_MARGIN_Y,
  CANVAS_W,
} from "./constellation";

describe("buildConstellation", () => {
  it("is deterministic — the same seed always yields the same geometry", () => {
    expect(buildConstellation(7, 11)).toEqual(buildConstellation(7, 11));
  });

  it("yields different geometry per seed", () => {
    expect(buildConstellation(1, 11)).not.toEqual(buildConstellation(2, 11));
  });

  it("keeps every star inside the margins and links each to an earlier star", () => {
    const { stars, edges } = buildConstellation(11, 12);

    const inBounds = stars.every(
      (s) =>
        s.x >= CANVAS_MARGIN_X &&
        s.x <= CANVAS_W - CANVAS_MARGIN_X &&
        s.y >= CANVAS_MARGIN_Y &&
        s.y <= CANVAS_H - CANVAS_MARGIN_Y,
    );
    expect(inBounds).toBe(true);
    // A connected, acyclic constellation: every star after the first links backwards.
    expect(edges).toHaveLength(stars.length - 1);
    for (const edge of edges) {
      expect(stars.indexOf(edge.to)).toBeLessThan(stars.indexOf(edge.from));
    }
  });

  it("caps the glow halos at the lit stars, at most three", () => {
    const { stars, halos } = buildConstellation(5, 14);
    expect(halos.length).toBeLessThanOrEqual(3);
    for (const halo of halos) expect(halo.isLit).toBe(true);
    expect(halos.length).toBeLessThanOrEqual(stars.filter((s) => s.isLit).length);
  });
});
