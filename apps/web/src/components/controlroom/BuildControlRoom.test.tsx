import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent } from "../../test/fixtures";
import { BuildControlRoom } from "./BuildControlRoom";

/** A mid-build stream: concepts done, graph in flight, with reasoning + a paired tool call. */
function midBuild() {
  return {
    topic: "How HTTPS works",
    events: [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("concepts_extracted", 1, { kcCount: 21, label: "21 concepts" }),
      makeProgressEvent("graph_built", 2, { kcCount: 21, edgeCount: 27, label: "27 edges" }),
    ],
    agentEvents: [
      makeAgentEvent("reasoning", 0, { stage: "run_started", text: "Planning the build…" }),
      makeAgentEvent("tool_call", 1, {
        stage: "run_started",
        tool: "extract_concepts",
        toolArgs: { topic: "HTTPS" },
      }),
      makeAgentEvent("tool_result", 2, {
        stage: "concepts_extracted",
        tool: "extract_concepts",
        result: "21 concepts",
      }),
    ],
  };
}

describe("BuildControlRoom", () => {
  it("lays out the control room: blueprint region, agent console, and instrument rail", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    expect(screen.getByRole("region", { name: /blueprint/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /agent console/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /pipeline/i })).toBeInTheDocument();
  });

  it("renders the real pipeline phases with the active phase and summaries", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    const pipeline = screen.getByRole("region", { name: /pipeline/i });
    // Concepts is done with its summary; Graph is the active (latest-stage) phase.
    expect(within(pipeline).getByText("Concepts")).toBeInTheDocument();
    expect(within(pipeline).getByText("21 concepts")).toBeInTheDocument();
    const graph = within(pipeline).getByText("Graph").closest("[data-status]");
    expect(graph).toHaveAttribute("data-status", "active");
  });

  it("tickers tool calls and reasoning through the agent console", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    const console = screen.getByRole("region", { name: /agent console/i });
    expect(within(console).getByText("Planning the build…")).toBeInTheDocument();
    expect(within(console).getByText("extract_concepts")).toBeInTheDocument();
    expect(within(console).getByText("21 concepts")).toBeInTheDocument();
  });

  it("keeps the full transcript one toggle away and returns", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    fireEvent.click(screen.getByRole("radio", { name: "Transcript" }));
    // The branded transcript (ToolCallCard's eyebrow) renders; the console strip is gone.
    expect(screen.getByText("Tool call")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /agent console/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Control room" }));
    expect(screen.getByRole("region", { name: /agent console/i })).toBeInTheDocument();
  });

  it("never leaks a JSON tool result into the ticker — the ✓ glyph carries completion", () => {
    const build = midBuild();
    build.agentEvents.push(
      makeAgentEvent("tool_call", 3, {
        stage: "concepts_extracted",
        tool: "build_prerequisite_graph",
        toolArgs: { goal: "https" },
      }),
      makeAgentEvent("tool_result", 4, {
        stage: "graph_built",
        tool: "build_prerequisite_graph",
        result: '{"nodes": [{"id": "tcp"', // truncated mid-stream, as it arrives in production
      }),
    );
    render(<BuildControlRoom {...build} />);

    expect(screen.queryByText(/"nodes":/)).not.toBeInTheDocument();
    expect(screen.getByText("build_prerequisite_graph")).toBeInTheDocument();
  });

  it("shows the blueprint fallback before any graph structure exists", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    // No structured graph payload on these events — the canvas says so instead of faking nodes.
    expect(
      within(screen.getByRole("region", { name: /blueprint/i })).getByText(
        /assembling the prerequisite graph/i,
      ),
    ).toBeInTheDocument();
  });
});
