import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { HeatDay } from "../../lib/activity";
import { ActivityHeat } from "./ActivityHeat";

function day(date: string, minutes: number, active: boolean): HeatDay {
  return { date, minutes, active };
}

describe("ActivityHeat", () => {
  it("lights active squares — including event-only days at the lowest step", () => {
    // Arrange — a minute-heavy day, an event-only day (0 minutes but active), and a quiet day.
    const heat = [
      day("2026-07-06", 40, true),
      day("2026-07-07", 0, true),
      day("2026-07-08", 0, false),
    ];

    // Act
    const { container } = render(<ActivityHeat heat={heat} />);

    // Assert — active squares carry the marker + an amber background; the event-only day still
    // reads as studied (lowest ramp step), the quiet day stays unstyled muted.
    const squares = Array.from(container.querySelectorAll("[title]"));
    expect(squares).toHaveLength(3);
    expect(squares[0]).toHaveAttribute("data-active");
    expect(squares[0]?.getAttribute("style")).toContain("color-mix");
    expect(squares[1]).toHaveAttribute("data-active");
    expect(squares[1]?.getAttribute("style")).toContain("18%");
    expect(squares[2]).not.toHaveAttribute("data-active");
    expect(squares[2]?.getAttribute("style")).toBeFalsy();
    // The honest caption counts studied days only.
    expect(screen.getByText(/studied 2 of the last 3 days/i)).toBeInTheDocument();
  });
});
