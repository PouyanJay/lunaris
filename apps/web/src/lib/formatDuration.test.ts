import { describe, expect, it } from "vitest";

import { formatDuration } from "./formatDuration";

describe("formatDuration", () => {
  it.each([
    [800, "0.8s"],
    [1500, "1.5s"],
    [12300, "12.3s"],
    // The boundary: anything under a minute stays in the seconds branch (59.999s → "60.0s").
    [59999, "60.0s"],
  ])("formats a sub-minute span %ims as %s", (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected);
  });

  it.each([
    [60000, "1m 0s"],
    [65000, "1m 5s"],
    [125000, "2m 5s"],
  ])("formats a minute-plus span %ims as %s", (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected);
  });

  it("carries rounding up cleanly instead of emitting 60s", () => {
    expect(formatDuration(119500)).toBe("2m 0s");
  });

  it("clamps a negative span (clock skew) to zero", () => {
    expect(formatDuration(-500)).toBe("0.0s");
  });
});
