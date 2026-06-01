import { fireEvent, render, screen, within } from "@testing-library/react";
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
  it("renders the leading Start node and every pipeline phase on the spine", () => {
    render(<BuildTimeline {...streamingProps()} />);

    for (const label of [
      "Start",
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

  it("pins the agent's plan at the top with a done/total progress count", () => {
    render(
      <BuildTimeline
        topic="X"
        events={[makeProgressEvent("concepts_extracted", 1)]}
        agentEvents={[
          makeAgentEvent("todo", 0, {
            stage: "run_started",
            todos: [
              { content: "Extract concepts", status: "completed" },
              { content: "Design curriculum", status: "in_progress" },
              { content: "Finalize the course", status: "pending" },
            ],
          }),
        ]}
      />,
    );

    // The plan panel lives inside the build timeline region (not floating elsewhere).
    const timeline = screen.getByRole("region", { name: /building x/i });
    const plan = within(timeline).getByRole("region", { name: /agent plan/i });
    expect(within(plan).getByText("Extract concepts")).toBeInTheDocument();
    expect(within(plan).getByText("Finalize the course")).toBeInTheDocument();
    // One of three plan items complete → the panel doubles as a coarse progress readout.
    expect(within(plan).getByText("1 / 3")).toBeInTheDocument();
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

  it("shows the elapsed duration on a done phase, but not on the active one", () => {
    render(
      <BuildTimeline
        {...streamingProps()}
        stageTimes={{ run_started: 1_000, concepts_extracted: 3_000, graph_built: 3_500 }}
      />,
    );

    // Concepts is done: run_started→concepts_extracted = 2.0s, shown in its header.
    const conceptsHeader = screen.getByRole("button", { name: /concepts — 21 concepts/i });
    expect(within(conceptsHeader).getByText("2.0s")).toBeInTheDocument();
    // Graph is active → it streams "running…", never a duration (even though both stamps exist).
    expect(screen.queryByText("0.5s")).not.toBeInTheDocument();
  });

  it("exposes the timeline as a focusable region with a live status and keyboard-operable toggles", () => {
    render(<BuildTimeline {...streamingProps()} />);

    // The scrollable timeline is reachable by keyboard, and announces the active phase via a live region.
    const region = screen.getByRole("region", { name: /building https/i });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("status")).toBeInTheDocument();
    // A phase with content collapses to a real <button> (Enter/Space operable natively); it is
    // expanded by default, so aria-expanded starts true.
    expect(screen.getByRole("button", { name: /concepts — 21 concepts/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("shows a done phase expanded by default and collapses it on click", () => {
    render(<BuildTimeline {...streamingProps()} />);

    // Concepts is done but EXPANDED by default — its tool entry shows without a click.
    const conceptsHeader = screen.getByRole("button", { name: /concepts — 21 concepts/i });
    expect(conceptsHeader).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();

    // Clicking collapses it; clicking again re-expands.
    fireEvent.click(conceptsHeader);
    expect(conceptsHeader).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("extract_concepts")).not.toBeInTheDocument();
    fireEvent.click(conceptsHeader);
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
  });

  it("streams reasoning token deltas into one growing beat with a live caret on the active phase", () => {
    // Graph is active and the agent's reasoning is forming token-by-token in it.
    render(
      <BuildTimeline
        topic="HTTPS"
        events={[makeProgressEvent("concepts_extracted", 1), makeProgressEvent("graph_built", 2)]}
        agentEvents={[
          makeAgentEvent("reasoning", 0, { stage: "graph_built", delta: "Ordering the " }),
          makeAgentEvent("reasoning", 1, { stage: "graph_built", delta: "prerequisites." }),
        ]}
      />,
    );

    // The deltas formed one beat (the full text, not a node per token), with a live caret beside it.
    expect(screen.getByText("Ordering the prerequisites.")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-caret")).toBeInTheDocument();
  });

  it("shows no caret once the streamed reasoning's phase is done", () => {
    // The same streamed reasoning, but its phase (Concepts) has completed — the caret is gone.
    render(
      <BuildTimeline
        topic="HTTPS"
        events={[makeProgressEvent("concepts_extracted", 1), makeProgressEvent("graph_built", 2)]}
        agentEvents={[
          makeAgentEvent("reasoning", 0, { stage: "concepts_extracted", delta: "Extracted " }),
          makeAgentEvent("reasoning", 1, { stage: "concepts_extracted", delta: "the concepts." }),
        ]}
      />,
    );

    expect(screen.getByText("Extracted the concepts.")).toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-caret")).not.toBeInTheDocument();
  });
});
