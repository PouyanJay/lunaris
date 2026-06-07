import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MayerFlags, Visual, VisualSpec } from "../../../types/course";
import { VisualRenderer } from "./VisualRenderer";

const NO_MAYER: MayerFlags = {
  coherence: false,
  signaling: false,
  spatialContiguity: false,
  redundancy: false,
};

function makeVisual(spec: VisualSpec | null, source = ""): Visual {
  return { kind: "mermaid", source, rendered: null, spec, mayerChecks: NO_MAYER };
}

describe("VisualRenderer", () => {
  it("renders a steps spec as ordered steps under its title", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "steps",
      title: "How it works",
      steps: [
        { title: "Compare", detail: "look at the middle" },
        { title: "Halve", detail: null },
      ],
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert — the title caption + each step (with detail) render.
    expect(screen.getByText("How it works")).toBeInTheDocument();
    expect(screen.getByText("Compare")).toBeInTheDocument();
    expect(screen.getByText("Halve")).toBeInTheDocument();
    expect(screen.getByText("look at the middle")).toBeInTheDocument();
  });

  it("renders a comparison spec as a table", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "comparison",
      title: null,
      columns: ["Speed", "Memory"],
      rows: [{ label: "Binary search", values: ["log n", "O(1)"] }],
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert — both column headers, the row label, and a cell value.
    expect(screen.getByText("Speed")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("Binary search")).toBeInTheDocument();
    expect(screen.getByText("log n")).toBeInTheDocument();
  });

  it("renders a timeline spec's events with their markers and detail", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "timeline",
      title: null,
      events: [{ label: "Sort first", detail: "ascending", when: "Step 1" }],
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert
    expect(screen.getByText("Sort first")).toBeInTheDocument();
    expect(screen.getByText("Step 1")).toBeInTheDocument();
    expect(screen.getByText("ascending")).toBeInTheDocument();
  });

  it("renders a flow spec's node labels on a canvas", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "flow",
      title: null,
      nodes: [
        { id: "a", label: "Start" },
        { id: "b", label: "Compare" },
      ],
      edges: [{ from: "a", to: "b", label: null }],
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert
    expect(screen.getByText("Start")).toBeInTheDocument();
    expect(screen.getByText("Compare")).toBeInTheDocument();
  });

  it("renders a tree spec's node labels on a canvas", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "tree",
      title: null,
      nodes: [
        { id: "r", label: "Root", parentId: null },
        { id: "c", label: "Child", parentId: "r" },
      ],
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert
    expect(screen.getByText("Root")).toBeInTheDocument();
    expect(screen.getByText("Child")).toBeInTheDocument();
  });

  it("renders a worked-example spec as a literal/improved pair with its note", () => {
    // Arrange
    const spec: VisualSpec = {
      type: "worked-example",
      title: "Worked Example 1",
      literal: {
        label: "Literal",
        content: "We will work very hard on this.",
        language: null,
        caption: null,
      },
      improved: {
        label: "With collocation",
        content: "We will do the heavy lifting on this.",
        language: null,
        caption: null,
      },
      note: "'do the heavy lifting' suits a professional tone.",
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert — the caption title, both labelled sides, and the explanatory note all render.
    expect(screen.getByText("Worked Example 1")).toBeInTheDocument();
    expect(screen.getByText("Literal")).toBeInTheDocument();
    expect(screen.getByText("We will work very hard on this.")).toBeInTheDocument();
    expect(screen.getByText("With collocation")).toBeInTheDocument();
    expect(screen.getByText("We will do the heavy lifting on this.")).toBeInTheDocument();
    expect(screen.getByText(/suits a professional tone/)).toBeInTheDocument();
  });

  it("renders a worked-example spec with a null note and no why row", () => {
    // Arrange — the renderer must forward note=null (not undefined/"") so the panel omits the row.
    const spec: VisualSpec = {
      type: "worked-example",
      title: null,
      literal: { label: "Vague", content: "The thing is bad.", language: null, caption: null },
      improved: {
        label: "Precise",
        content: "Transit cuts commute time by 30%.",
        language: null,
        caption: null,
      },
      note: null,
    };

    // Act
    render(<VisualRenderer visual={makeVisual(spec)} />);

    // Assert — both sides render, but there is no "Why" note row.
    expect(screen.getByText("Transit cuts commute time by 30%.")).toBeInTheDocument();
    expect(screen.queryByText("Why")).not.toBeInTheDocument();
  });

  it("falls back to the diagram source when there is no spec", () => {
    // Arrange / Act
    render(<VisualRenderer visual={makeVisual(null, "graph TD\n  A-->B")} />);

    // Assert
    expect(screen.getByText(/graph TD/)).toBeInTheDocument();
  });

  it("renders nothing when there is neither a spec nor a source", () => {
    // Arrange / Act
    const { container } = render(<VisualRenderer visual={makeVisual(null, "")} />);

    // Assert
    expect(container).toBeEmptyDOMElement();
  });
});
