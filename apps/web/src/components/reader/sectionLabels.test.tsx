import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("section labels (R1)", () => {
  it("lifts a leading ALL-CAPS 'LABEL:' into an eyebrow section head, body preserved verbatim", () => {
    const { container } = render(
      <Markdown>{"STRATEGY: Build the cascade from the airway surface downward."}</Markdown>,
    );

    // The label becomes a heading-role element carrying the label word (colon dropped).
    const label = screen.getByRole("heading", { name: /strategy/i });
    expect(label.textContent).toContain("STRATEGY");
    expect(label.textContent).not.toContain(":");

    // The body sentence survives verbatim, as its own block, without the label.
    expect(container.textContent).toContain("Build the cascade from the airway surface downward.");
    expect(label.textContent).not.toContain("Build the cascade");
  });

  it("keeps a '(qualifier)' as a separate muted span on the label", () => {
    render(<Markdown>{"UPSTREAM LAYER (alarmins): epithelial cells release alarmins."}</Markdown>);

    const label = screen.getByRole("heading", { name: /upstream layer/i });
    expect(within(label).getByText("alarmins")).toBeInTheDocument();
    expect(label.textContent).toContain("UPSTREAM LAYER");
  });
});
