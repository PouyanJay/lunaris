import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CostChart } from "./CostChart";

describe("CostChart", () => {
  it("renders an empty state when there are no points", () => {
    render(<CostChart points={[]} currency="CAD" />);

    expect(screen.getByText(/No cost data/)).toBeInTheDocument();
  });

  it("renders a bar per day and a labelled chart, flagging the partial day", () => {
    const points = [
      { day: "2026-06-24", amount: 2, isPartial: false },
      { day: "2026-06-25", amount: 5, isPartial: false },
      { day: "2026-06-26", amount: 1, isPartial: true },
    ];
    render(<CostChart points={points} currency="CAD" />);

    // An accessible bar chart with a per-day data table for screen readers.
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.getByText("2026-06-26 (partial)")).toBeInTheDocument();
  });
});
