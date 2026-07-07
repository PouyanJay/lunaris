import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CourseCover } from "./CourseCover";

describe("CourseCover", () => {
  it("is deterministic — the same seed always draws the same constellation", () => {
    const first = renderToStaticMarkup(<CourseCover seed={7} />);
    const second = renderToStaticMarkup(<CourseCover seed={7} />);
    expect(first).toBe(second);
  });

  it("draws a different constellation per seed", () => {
    const a = renderToStaticMarkup(<CourseCover seed={1} />);
    const b = renderToStaticMarkup(<CourseCover seed={2} />);
    expect(a).not.toBe(b);
  });

  it("scales the star count with the nodes option", () => {
    const sparse = renderToStaticMarkup(<CourseCover seed={3} nodes={5} />);
    const dense = renderToStaticMarkup(<CourseCover seed={3} nodes={14} />);
    const circles = (svg: string) => (svg.match(/<circle/g) ?? []).length;
    expect(circles(dense)).toBeGreaterThan(circles(sparse));
  });

  it("is decorative: hidden from assistive tech and unfocusable", () => {
    const svg = renderToStaticMarkup(<CourseCover seed={4} />);
    expect(svg).toContain('aria-hidden="true"');
    expect(svg).toContain('focusable="false"');
  });

  it("keeps every star inside the canvas bounds", () => {
    const svg = renderToStaticMarkup(<CourseCover seed={11} />);
    const coords = [...svg.matchAll(/<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"/g)];
    expect(coords.length).toBeGreaterThan(0);
    for (const [, cx, cy] of coords) {
      expect(Number(cx)).toBeGreaterThanOrEqual(0);
      expect(Number(cx)).toBeLessThanOrEqual(400);
      expect(Number(cy)).toBeGreaterThanOrEqual(0);
      expect(Number(cy)).toBeLessThanOrEqual(230);
    }
  });
});
