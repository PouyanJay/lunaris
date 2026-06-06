import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Visual } from "../../../types/course";
import { VisualRenderer } from "./VisualRenderer";

/** A before-after Visual as it arrives from the course artifact. */
function beforeAfterVisual(): Visual {
  return {
    kind: "spec",
    source: "",
    rendered: null,
    mayerChecks: { coherence: true, signaling: true, spatialContiguity: true, redundancy: false },
    spec: {
      type: "before-after",
      title: "From linear to binary search",
      before: { label: "Before", content: "scan every element" },
      after: { label: "After", content: "halve the search space" },
    },
  };
}

describe("BeforeAfter visual", () => {
  it("renders a two-tab toggle and shows the 'before' side first", () => {
    render(<VisualRenderer visual={beforeAfterVisual()} />);

    const tablist = screen.getByRole("tablist");
    const tabs = within(tablist).getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveAccessibleName("Before");
    expect(tabs[1]).toHaveAccessibleName("After");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("scan every element");
  });

  it("toggles to the 'after' side on click", () => {
    render(<VisualRenderer visual={beforeAfterVisual()} />);

    const after = within(screen.getByRole("tablist")).getAllByRole("tab")[1]!;
    fireEvent.click(after);

    expect(after).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveTextContent("halve the search space");
    expect(panel).not.toHaveTextContent("scan every element");
  });
});
