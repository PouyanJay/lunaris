import { describe, expect, it } from "vitest";

import type { HeatDay } from "./activity";
import { deriveTodayMinutes } from "./trailMinutes";

function heatDay(date: string, minutes: number): HeatDay {
  return { date, minutes, active: minutes > 0 };
}

/** Local (no trailing Z), so the frozen "today" is the same calendar day in every timezone. */
const NOW = new Date("2026-07-20T18:00:00");

describe("deriveTodayMinutes", () => {
  it("reads the minutes recorded for today's local day", () => {
    // Arrange
    const heat = [heatDay("2026-07-19", 12), heatDay("2026-07-20", 24)];

    // Act / Assert
    expect(deriveTodayMinutes(heat, NOW)).toBe(24);
  });

  it("ignores minutes recorded on other days", () => {
    // Arrange — only yesterday has minutes.
    const heat = [heatDay("2026-07-19", 40)];

    // Act / Assert
    expect(deriveTodayMinutes(heat, NOW)).toBe(0);
  });

  it("returns zero when today has no bucket", () => {
    // Arrange / Act / Assert
    expect(deriveTodayMinutes([], NOW)).toBe(0);
  });
});
