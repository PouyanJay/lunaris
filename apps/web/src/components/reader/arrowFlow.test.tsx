import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ASTHMA_PROSE } from "./lessonProse.fixture";
import { Markdown } from "./Markdown";

/** R3 — an inline arrow chain "A → B → C" (>=2 arrows) becomes a numbered, ordered-list flow, with
 *  the lead-in and trailing sentence kept as prose around it. */
describe("arrow flow (R3)", () => {
  it("turns a 3-node chain into an ordered list, keeping lead-in and trailing prose", () => {
    // The chain ends at a sentence boundary; a following sentence stays as trailing prose.
    render(<Markdown>{"The pathway is A → B → C. Then it stops."}</Markdown>);

    const flow = screen.getByRole("list", { name: /step chain/i });
    const items = within(flow).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["A", "B", "C"]);

    // Lead-in survives as prose (with the "is" cue), not swallowed into the first node.
    expect(screen.getByText(/The pathway is/)).toBeInTheDocument();
    expect(items[0]!.textContent).toBe("A");
    expect(screen.getByText(/Then it stops\./)).toBeInTheDocument();
  });

  it("keeps a comma-series inside the final node intact (ends only at the sentence period)", () => {
    render(<Markdown>{"The route is start → middle → left, right, and center. Done."}</Markdown>);

    const items = within(screen.getByRole("list", { name: /step chain/i })).getAllByRole(
      "listitem",
    );
    expect(items).toHaveLength(3);
    expect(items[2]!.textContent).toBe("left, right, and center");
    expect(screen.getByText(/Done\./)).toBeInTheDocument();
  });

  it("lifts the reference worked-example chain into a 7-node flow", () => {
    render(<Markdown>{ASTHMA_PROSE}</Markdown>);

    const flow = screen.getByRole("list", { name: /step chain/i });
    const items = within(flow).getAllByRole("listitem");
    expect(items).toHaveLength(7);
    expect(items[0]!.textContent).toBe("trigger");
    expect(items[6]!.textContent).toMatch(/hyperresponsiveness/);
    // The closing sentence stays as prose after the flow.
    expect(screen.getByText(/each node is a druggable biologic target/)).toBeInTheDocument();
  });

  describe("does NOT fire (conservative)", () => {
    it("leaves a single arrow (2 nodes) as prose", () => {
      render(<Markdown>{"Input maps to output as A → B in one hop."}</Markdown>);
      expect(screen.queryByRole("list", { name: /step chain/i })).toBeNull();
      expect(screen.getByText(/A → B/)).toBeInTheDocument();
    });

    it("leaves ordinary prose with no arrows alone", () => {
      render(<Markdown>{"The cascade proceeds from the surface down to the muscle."}</Markdown>);
      expect(screen.queryByRole("list", { name: /step chain/i })).toBeNull();
    });
  });
});
