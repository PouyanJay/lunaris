import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GraphLegend } from "./GraphLegend";

describe("GraphLegend", () => {
  it("reads the difficulty ramp and the learning-state key", () => {
    render(<GraphLegend />);
    const legend = screen.getByLabelText("Legend");

    expect(within(legend).getByText("Difficulty")).toBeInTheDocument();
    expect(within(legend).getByText("easier → harder")).toBeInTheDocument();
    // The state key mirrors the node badges: mastered / up next dots + the goal ring.
    expect(within(legend).getByText("mastered")).toBeInTheDocument();
    expect(within(legend).getByText("up next")).toBeInTheDocument();
    expect(within(legend).getByText("goal")).toBeInTheDocument();
    // The retired KNOWN marker stays gone.
    expect(within(legend).queryByText(/known/i)).not.toBeInTheDocument();
  });
});
