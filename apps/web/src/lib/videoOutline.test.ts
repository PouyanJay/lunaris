import { describe, expect, it } from "vitest";

import { activeSpanIndex } from "./videoOutline";

const SPANS = [
  { startS: 0, endS: 2 },
  { startS: 2, endS: 5 },
  { startS: 5, endS: 8 },
];

describe("activeSpanIndex", () => {
  it("finds the span containing the current time", () => {
    expect(activeSpanIndex(SPANS, 0)).toBe(0);
    expect(activeSpanIndex(SPANS, 1.9)).toBe(0);
    expect(activeSpanIndex(SPANS, 2)).toBe(1);
    expect(activeSpanIndex(SPANS, 6.5)).toBe(2);
  });

  it("clamps past the end to the last span", () => {
    expect(activeSpanIndex(SPANS, 999)).toBe(2);
  });

  it("returns -1 for an empty list", () => {
    expect(activeSpanIndex([], 3)).toBe(-1);
  });

  it("treats a negative time as the first span", () => {
    expect(activeSpanIndex(SPANS, -1)).toBe(0);
  });
});
