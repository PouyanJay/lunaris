import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** R6 — break an over-long paragraph into smaller ones at sentence boundaries, so no block is a wall.
 *  Presentation-only: it never splits mid-sentence and never changes words. */
describe("paragraph rhythm (R6)", () => {
  const LONG =
    "The first idea is that systems evolve slowly over many cycles, and each cycle refines the " +
    "structure a little further. The second idea is that feedback loops stabilize the whole " +
    "arrangement once it forms and settles. The third idea is that small perturbations rarely " +
    "change the eventual outcome because the attractor is strong. The final idea is that observers " +
    "can predict the trajectory with only partial information about the starting state.";

  it("splits a long multi-sentence paragraph into at least two paragraphs", () => {
    const { container } = render(<Markdown>{LONG}</Markdown>);
    expect(container.querySelectorAll("p").length).toBeGreaterThanOrEqual(2);
  });

  it("preserves the wording verbatim across the split", () => {
    const { container } = render(<Markdown>{LONG}</Markdown>);
    const flat = (container.textContent ?? "").replace(/\s+/g, " ").trim();
    expect(flat).toBe(LONG.replace(/\s+/g, " ").trim());
  });

  it("leaves a short paragraph as a single paragraph", () => {
    const { container } = render(
      <Markdown>{"The cell divides in two. The tissue then grows outward."}</Markdown>,
    );
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("never splits a single long sentence mid-way", () => {
    const oneSentence =
      "This is a single sustained sentence that runs on with clause after clause about the " +
      "structure and the feedback and the slow evolution and the strong attractor and the partial " +
      "information right up until it finally stops.";
    const { container } = render(<Markdown>{oneSentence}</Markdown>);
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });
});
