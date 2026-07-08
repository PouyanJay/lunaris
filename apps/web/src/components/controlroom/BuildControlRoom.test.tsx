import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeCourse, makeProgressEvent } from "../../test/fixtures";
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

    const consolePanel = screen.getByRole("region", { name: /agent console/i });
    expect(within(consolePanel).getByText("Planning the build…")).toBeInTheDocument();
    expect(within(consolePanel).getByText("extract_concepts")).toBeInTheDocument();
    expect(within(consolePanel).getByText("21 concepts")).toBeInTheDocument();
  });

  it("glyphs the honesty states: pending tool ●, rejected source ✕", () => {
    const build = midBuild();
    build.agentEvents.push(
      // An unpaired call — still running.
      makeAgentEvent("tool_call", 3, {
        stage: "graph_built",
        tool: "build_prerequisite_graph",
        toolArgs: {},
      }),
      // A vetted-and-rejected discovery source.
      makeAgentEvent("source_evaluated", 4, {
        stage: "grounding_discovered",
        source: {
          kcId: "kc-1",
          domain: "content-farm.example",
          trustTier: "open",
          credibility: 0.2,
          sourceType: "web",
          accepted: false,
          reason: "low credibility",
        },
      }),
    );
    render(<BuildControlRoom {...build} />);

    const consolePanel = screen.getByRole("region", { name: /agent console/i });
    expect(within(consolePanel).getByText("●")).toBeInTheDocument();
    expect(within(consolePanel).getByText("running")).toBeInTheDocument(); // sr-only state text
    expect(within(consolePanel).getByText("✕")).toBeInTheDocument();
    expect(within(consolePanel).getByText(/rejected · open/)).toBeInTheDocument();
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

  it("assembles the live blueprint from the structured graph event", async () => {
    // The T1 payloads: graph structure + module mapping + one authored module → the canvas
    // shows real nodes with their assembly states and the honest mapped counter.
    const build = midBuild();
    build.events.push(
      makeProgressEvent("graph_built", 3, {
        graph: makeCourse().graph,
        goalConcept: "binary_search",
      }),
      makeProgressEvent("curriculum_designed", 4, {
        modules: [
          { id: "m-one", title: "Foundations", kcs: ["comparison", "sorted_order"] },
          { id: "m-two", title: "Search", kcs: ["binary_search"] },
        ],
      }),
      makeProgressEvent("module_authored", 5, { moduleId: "m-one" }),
    );
    render(<BuildControlRoom {...build} />);

    // React Flow keeps nodes visibility:hidden in jsdom — assert the aria-label attributes.
    await waitFor(() =>
      expect(
        document.querySelector('[aria-label*="Comparison."][aria-label*="Mapped."]'),
      ).not.toBeNull(),
    );
    expect(
      document.querySelector('[aria-label*="Binary Search."][aria-label*="Mapping."]'),
    ).not.toBeNull();
    // The goal node keeps its GOAL badge whatever its assembly state.
    expect(
      document.querySelector('[aria-label*="Binary Search."][aria-label*="Course goal."]'),
    ).not.toBeNull();
    expect(screen.getByText("2 / 3 mapped")).toBeInTheDocument();
    expect(screen.queryByText(/appears here as concepts are mapped/i)).not.toBeInTheDocument();
  });

  it("holds unreached concepts queued before authoring starts", async () => {
    const build = midBuild();
    build.events.push(
      makeProgressEvent("graph_built", 3, {
        graph: makeCourse().graph,
        goalConcept: "binary_search",
      }),
      makeProgressEvent("curriculum_designed", 4, {
        modules: [{ id: "m-one", title: "Foundations", kcs: ["comparison"] }],
      }),
    );
    render(<BuildControlRoom {...build} />);

    await waitFor(() =>
      expect(
        document.querySelector('[aria-label*="Comparison."][aria-label*="Queued."]'),
      ).not.toBeNull(),
    );
    expect(screen.getByText("0 / 3 mapped")).toBeInTheDocument();
  });

  it("reads the grounding ledger and the honest scorecard off the rail", () => {
    const build = midBuild();
    build.events.push(
      makeProgressEvent("claims_verified", 3, {
        claimsTotal: 10,
        claimsSupported: 8,
        claimsCut: 2,
      }),
      makeProgressEvent("coverage_verified", 4, { gapCount: 0 }),
    );
    build.agentEvents.push(
      makeAgentEvent("source_evaluated", 3, {
        stage: "grounding_discovered",
        source: {
          kcId: "kc-1",
          domain: "rfc-editor.org",
          trustTier: "official",
          credibility: 0.94,
          sourceType: "reference",
          accepted: true,
          reason: "",
        },
      }),
    );
    render(<BuildControlRoom {...build} />);

    const ledger = screen.getByRole("region", { name: /grounding ledger/i });
    expect(within(ledger).getByText("8")).toBeInTheDocument();
    expect(within(ledger).getByText("2")).toBeInTheDocument();
    expect(within(ledger).getByText(/official 100%/i)).toBeInTheDocument();

    const scorecard = screen.getByRole("region", { name: /readiness scorecard/i });
    expect(within(scorecard).getByText("Grounding")).toBeInTheDocument();
    expect(within(scorecard).getByText("80%")).toBeInTheDocument();
    expect(within(scorecard).getByText("no gaps")).toBeInTheDocument();
    // Structure/Trust-less fixtures: no graph payload, so no Structure gauge — no fake gauges.
    expect(within(scorecard).queryByText("Structure")).not.toBeInTheDocument();
  });

  it("shows the blueprint fallback before any graph structure exists", () => {
    const build = midBuild();
    render(<BuildControlRoom {...build} />);

    // No structured graph payload on these events — the canvas says so instead of faking nodes,
    // and the scorecard region doesn't exist until a gauge has a real reading.
    expect(
      within(screen.getByRole("region", { name: /blueprint/i })).getByText(
        /assembling the prerequisite graph/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: /readiness scorecard/i }),
    ).not.toBeInTheDocument();
  });
});
