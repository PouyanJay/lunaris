import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import sampleCourse from "../../../../public/sample-course.json";
import { parseCourse } from "../../../lib/loadCourse";
import type { TransformSide, Visual } from "../../../types/course";
import { VisualRenderer } from "./VisualRenderer";

const DEFAULT_BEFORE: TransformSide = {
  label: "Before",
  content: "scan every element",
  language: null,
  caption: null,
};
const DEFAULT_AFTER: TransformSide = {
  label: "After",
  content: "halve the search space",
  language: null,
  caption: null,
};

/** A before-after Visual as it arrives from the course artifact, with overridable sides. */
function beforeAfterVisual(over: { before?: TransformSide; after?: TransformSide } = {}): Visual {
  return {
    kind: "spec",
    source: "",
    rendered: null,
    mayerChecks: { coherence: true, signaling: true, spatialContiguity: true, redundancy: false },
    spec: {
      type: "before-after",
      title: "From linear to binary search",
      before: over.before ?? DEFAULT_BEFORE,
      after: over.after ?? DEFAULT_AFTER,
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

  it("renders a code-bearing side in a <pre><code> block with its caption", () => {
    const visual = beforeAfterVisual({
      before: {
        label: "Naive",
        content: "for x in xs:\n    if x == target: ...",
        language: "python",
        caption: "O(n) per lookup",
      },
    });
    render(<VisualRenderer visual={visual} />);

    const panel = screen.getByRole("tabpanel");
    const code = panel.querySelector("pre code");
    expect(code).not.toBeNull();
    expect(code).toHaveTextContent("if x == target");
    expect(panel).toHaveTextContent("O(n) per lookup");
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

  it("switches sides with the arrow keys (via the reused Tabs primitive)", () => {
    render(<VisualRenderer visual={beforeAfterVisual()} />);

    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    tabs[0]!.focus();
    fireEvent.keyDown(tabs[0]!, { key: "ArrowRight" });

    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("halve the search space");
  });

  it("omits the caption element when a side has none", () => {
    render(<VisualRenderer visual={beforeAfterVisual()} />);

    // The default sides carry no caption, so no caption element is rendered (semantic, not a node count).
    expect(screen.queryByTestId("side-caption")).toBeNull();
  });

  it("renders the before-after visual embedded in the real sample course", () => {
    // Output verification on the real artifact: the JSON survives the loader and renders the toggle.
    const course = parseCourse(sampleCourse);
    const visual = course.modules[0]!.lessons[0]!.segments.demonstrate.visuals[0]!;
    expect(visual.spec?.type).toBe("before-after");

    render(<VisualRenderer visual={visual} />);

    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Linear scan", "Binary search"]);
    expect(screen.getByRole("tabpanel").querySelector("pre code")).not.toBeNull();
  });
});
