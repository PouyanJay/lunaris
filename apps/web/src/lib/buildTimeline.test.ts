import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent } from "../test/fixtures";
import { buildTimeline, type TimelinePhase } from "./buildTimeline";

/** Find a phase by its label, failing loudly if absent. */
function phase(phases: TimelinePhase[], label: string): TimelinePhase {
  const found = phases.find((p) => p.label === label);
  if (!found) throw new Error(`no "${label}" phase in [${phases.map((p) => p.label).join(", ")}]`);
  return found;
}

describe("buildTimeline", () => {
  it("buckets agent events under the phase active when they fired, pairing call+result", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("concepts_extracted", 1, { kcCount: 21, label: "21 concepts" }),
      makeProgressEvent("graph_built", 2),
    ];
    const agentEvents = [
      makeAgentEvent("reasoning", 0, { stage: "run_started", text: "Planning the build…" }),
      makeAgentEvent("tool_call", 1, {
        stage: "run_started",
        tool: "extract_concepts",
        toolArgs: { topic: "HTTPS" },
      }),
      // The result lands in the NEXT phase — the pair must follow the result's stage (Concepts).
      makeAgentEvent("tool_result", 2, {
        stage: "concepts_extracted",
        tool: "extract_concepts",
        result: "21 concepts",
      }),
      makeAgentEvent("tool_call", 3, {
        stage: "concepts_extracted",
        tool: "build_prerequisite_graph",
      }),
      makeAgentEvent("tool_result", 4, {
        stage: "graph_built",
        tool: "build_prerequisite_graph",
        result: "ok",
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // The pre-stage beat is in the intro "Plan" node.
    const intro = phase(phases, "Plan");
    expect(intro.entries).toEqual([
      expect.objectContaining({ kind: "reasoning", text: "Planning the build…" }),
    ]);

    // extract_concepts pairs into Concepts (by the result's stage), carrying its result; done.
    const concepts = phase(phases, "Concepts");
    expect(concepts.status).toBe("done");
    expect(concepts.summary).toBe("21 concepts");
    expect(concepts.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "extract_concepts", result: "21 concepts" }),
    ]);

    // The graph tool pairs into Graph; it's the latest reached phase → active.
    const graph = phase(phases, "Graph");
    expect(graph.status).toBe("active");
    expect(graph.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "build_prerequisite_graph", result: "ok" }),
    ]);

    // Unreached phases are pending and empty.
    expect(phase(phases, "Curriculum").status).toBe("pending");
    expect(phase(phases, "Curriculum").entries).toHaveLength(0);
  });

  it("marks every phase done once the run completes", () => {
    const phases = buildTimeline([makeProgressEvent("run_completed", 9)], []);

    expect(phase(phases, "Concepts").status).toBe("done");
    expect(phase(phases, "Publish").status).toBe("done");
  });

  it("keeps a still-running tool call in its phase, unpaired", () => {
    const phases = buildTimeline(
      [makeProgressEvent("module_authored", 4)],
      [makeAgentEvent("tool_call", 0, { stage: "module_authored", tool: "task" })],
    );

    expect(phase(phases, "Lessons").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "task", result: null }),
    ]);
  });

  it("returns the six pending phases (no intro node) for an empty build", () => {
    const phases = buildTimeline([], []);

    expect(phases.map((p) => p.label)).toEqual([
      "Concepts",
      "Graph",
      "Curriculum",
      "Lessons",
      "Verify",
      "Publish",
    ]);
    expect(phases.every((p) => p.status === "pending" && p.entries.length === 0)).toBe(true);
  });

  it("pairs a result with the most recent open call of the same tool", () => {
    const events = [makeProgressEvent("module_authored", 4)];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "module_authored", tool: "task" }),
      makeAgentEvent("tool_call", 1, { stage: "module_authored", tool: "task" }),
      makeAgentEvent("tool_result", 2, {
        stage: "module_authored",
        tool: "task",
        result: "module 2 done",
      }),
    ];

    // Two open calls, one result → the newest call is paired; the older stays open.
    expect(phase(buildTimeline(events, agentEvents), "Lessons").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "task", result: null }),
      expect.objectContaining({ kind: "tool", tool: "task", result: "module 2 done" }),
    ]);
  });

  it("times each DONE phase from its stage arrival back to the previous stage", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("concepts_extracted", 1),
      makeProgressEvent("graph_built", 2),
    ];
    // Concepts spanned run_started→concepts_extracted (1.5s); Graph is still active.
    const stageTimes = { run_started: 1_000, concepts_extracted: 2_500, graph_built: 3_000 };

    const phases = buildTimeline(events, [], stageTimes);

    expect(phase(phases, "Concepts").durationMs).toBe(1_500);
    // The active phase shows "running…", not a duration; every unreached phase has none either.
    expect(phase(phases, "Graph").durationMs).toBeNull();
    expect(phases.filter((p) => p.status === "pending").every((p) => p.durationMs === null)).toBe(
      true,
    );
  });

  it("leaves a done phase's duration null when its lower-boundary stage time is missing", () => {
    // The client reconnected after run_started fired: Concepts' completion time is known, its start
    // (run_started) is not → no honest span to show.
    const phases = buildTimeline(
      [makeProgressEvent("concepts_extracted", 1), makeProgressEvent("graph_built", 2)],
      [],
      { concepts_extracted: 5_000, graph_built: 6_000 },
    );

    expect(phase(phases, "Concepts").status).toBe("done");
    expect(phase(phases, "Concepts").durationMs).toBeNull();
  });

  it("leaves durations null when no stage times are provided", () => {
    const phases = buildTimeline([makeProgressEvent("run_completed", 9)], []);

    expect(phases.every((p) => p.durationMs === null)).toBe(true);
  });

  it("surfaces an orphan tool result that has no preceding call", () => {
    const phases = buildTimeline(
      [makeProgressEvent("graph_built", 2)],
      [
        makeAgentEvent("tool_result", 0, {
          stage: "graph_built",
          tool: "build_prerequisite_graph",
          result: "ok",
        }),
      ],
    );

    expect(phase(phases, "Graph").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "build_prerequisite_graph", result: "ok" }),
    ]);
  });
});
