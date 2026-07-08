import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WeekDay } from "../../lib/activity";
import { ActivityWeekBars } from "./ActivityWeekBars";

function localIso(daysFromToday: number): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysFromToday);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

describe("ActivityWeekBars", () => {
  it("marks today's bar as the accent and zero days as empty", () => {
    // Arrange — a week ending today: yesterday studied, today studied, the rest quiet.
    const week: WeekDay[] = [
      { date: localIso(-6), minutes: 0 },
      { date: localIso(-5), minutes: 0 },
      { date: localIso(-4), minutes: 0 },
      { date: localIso(-3), minutes: 0 },
      { date: localIso(-2), minutes: 0 },
      { date: localIso(-1), minutes: 20 },
      { date: localIso(0), minutes: 33 },
    ];

    // Act
    const { container } = render(<ActivityWeekBars week={week} />);

    // Assert — exactly one accent bar (today), zero-minute days wear the empty marker, and a
    // studied past day wears neither (the deep-amber default).
    const bars = Array.from(container.querySelectorAll("[data-today], [data-empty]"));
    const todayBars = container.querySelectorAll("[data-today]");
    expect(todayBars).toHaveLength(1);
    expect(todayBars[0]).not.toHaveAttribute("data-empty");
    expect(container.querySelectorAll("[data-empty]")).toHaveLength(5);
    expect(bars).toHaveLength(6);
  });
});
