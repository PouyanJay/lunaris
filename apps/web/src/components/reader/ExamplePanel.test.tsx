import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("example panel", () => {
  it("lifts a cued example quote into its own panel, keeping the lead-in and continuation as prose", () => {
    const prose =
      "In a casual text to a friend, you might write: " +
      "'We need better transit because cars pollute and traffic is bad.' " +
      "But to decision-makers, vagueness costs credibility.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const panel = screen.getByRole("complementary", { name: "Example" });
    expect(panel).toHaveTextContent(
      "We need better transit because cars pollute and traffic is bad.",
    );
    // The lead-in cue stays above as prose; the continuation stays below.
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs[0]).toHaveTextContent(/you might write:$/);
    expect(container.textContent).toContain("But to decision-makers, vagueness costs credibility.");
    // The quoted example is no longer inline in the lead-in paragraph.
    expect(paragraphs[0]).not.toHaveTextContent("We need better transit");
  });

  it("leaves a short quoted term in the prose (no example panel)", () => {
    const prose =
      "In climate science, 'mitigation' means reducing emissions, not lessening severity.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(screen.queryByRole("complementary", { name: "Example" })).toBeNull();
    expect(within(container).getByText(/mitigation/)).toBeInTheDocument();
  });
});
