import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent } from "../../test/fixtures";
import { BuildTimeline } from "./BuildTimeline";

/** A build mid-flight: a pre-stage plan beat, Concepts finished, Graph in progress. */
function streamingProps() {
  return {
    topic: "HTTPS",
    events: [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("concepts_extracted", 1, { label: "21 concepts" }),
      makeProgressEvent("graph_built", 2),
    ],
    agentEvents: [
      makeAgentEvent("reasoning", 0, { stage: null, text: "Planning the build first." }),
      makeAgentEvent("tool_call", 1, { stage: "concepts_extracted", tool: "extract_concepts" }),
      makeAgentEvent("tool_result", 2, {
        stage: "concepts_extracted",
        tool: "extract_concepts",
        result: "21 concepts extracted",
      }),
      makeAgentEvent("reasoning", 3, { stage: "graph_built", text: "Ordering the prerequisites." }),
      makeAgentEvent("tool_call", 4, { stage: "graph_built", tool: "build_prerequisite_graph" }),
    ],
  };
}

describe("BuildTimeline", () => {
  it("renders the intro and every pipeline phase as a node on the spine", () => {
    render(<BuildTimeline {...streamingProps()} />);

    for (const label of [
      "Plan",
      "Concepts",
      "Graph",
      "Curriculum",
      "Lessons",
      "Verify",
      "Publish",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("shows a Starting… status before any phase is active", () => {
    render(<BuildTimeline topic="X" events={[]} agentEvents={[]} />);

    expect(screen.getByRole("status")).toHaveTextContent(/starting…/i);
  });

  it("expands and streams the active phase, and announces it", () => {
    render(<BuildTimeline {...streamingProps()} />);

    // Graph is the active phase: its reasoning + the in-flight tool call are visible.
    expect(screen.getByText("Ordering the prerequisites.")).toBeInTheDocument();
    expect(screen.getByText("build_prerequisite_graph")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/building: graph/i);
  });

  it("collapses a done phase to its summary and re-opens it on click", () => {
    render(<BuildTimeline {...streamingProps()} />);

    // Concepts is done: its summary shows, but its tool entry is collapsed away.
    expect(screen.getByText("21 concepts")).toBeInTheDocument();
    expect(screen.queryByText("extract_concepts")).not.toBeInTheDocument();

    // Clicking the phase header reveals its entries and flips the expanded state.
    const conceptsHeader = screen.getByRole("button", { name: /concepts — 21 concepts/i });
    expect(conceptsHeader).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(conceptsHeader);
    expect(conceptsHeader).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
  });
});
