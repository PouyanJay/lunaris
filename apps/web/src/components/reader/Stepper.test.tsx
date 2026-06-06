import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StepItem } from "./StepItem";
import { Stepper } from "./Stepper";

describe("Stepper", () => {
  it("lays out steps as a labelled ordered list with numbered headings", () => {
    render(
      <Stepper>
        <StepItem number="1" heading="Step 1: Gather terms">
          <p>Body one.</p>
        </StepItem>
        <StepItem number="2" heading="Step 2: Draft">
          <p>Body two.</p>
        </StepItem>
      </Stepper>,
    );

    const list = screen.getByRole("list", { name: "Steps" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Step 1: Gather terms")).toBeInTheDocument();
    expect(screen.getByText("Body two.")).toBeInTheDocument();
  });

  it("toggles a step's done state from its numbered node", () => {
    render(
      <StepItem number="2" heading="Step 2: Draft">
        <p>Write the argument.</p>
      </StepItem>,
    );

    const toggle = screen.getByRole("button", { name: /mark step 2 done/i });
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(toggle);

    // The pressed state carries completion (not colour alone); the label flips to "done".
    const done = screen.getByRole("button", { name: /step 2 done/i });
    expect(done).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(done);
    expect(screen.getByRole("button", { name: /mark step 2 done/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});
