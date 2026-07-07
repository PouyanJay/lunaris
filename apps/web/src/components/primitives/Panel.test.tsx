import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Panel } from "./Panel";

describe("Panel", () => {
  it("renders children inside the subtle variant by default", () => {
    render(
      <Panel aria-label="Setup">
        <p>Body copy</p>
      </Panel>,
    );
    const panel = screen.getByRole("region", { name: "Setup" });
    expect(panel).toHaveAttribute("data-variant", "subtle");
    expect(panel).toHaveTextContent("Body copy");
  });

  it("shows a header row only when a heading is given", () => {
    const { rerender } = render(<Panel heading="Level" cue="inferred" />);
    expect(screen.getByText("Level")).toBeInTheDocument();
    expect(screen.getByText("inferred")).toBeInTheDocument();

    rerender(<Panel>headless</Panel>);
    expect(screen.queryByText("Level")).not.toBeInTheDocument();
  });

  it("applies the requested variant", () => {
    render(<Panel variant="raised" heading="Grounding" />);
    expect(screen.getByText("Grounding").closest("section")).toHaveAttribute(
      "data-variant",
      "raised",
    );
  });
});
