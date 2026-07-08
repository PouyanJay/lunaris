import { describe, expect, it } from "vitest";

import { blueprintFromEvents } from "./blueprint";
import { makeCourse, makeProgressEvent } from "../test/fixtures";

const GRAPH = makeCourse().graph; // comparison → sorted_order → binary_search

function graphEvent(sequence = 1) {
  return makeProgressEvent("graph_built", sequence, {
    graph: GRAPH,
    goalConcept: "binary_search",
    kcCount: 3,
    edgeCount: 2,
  });
}

function curriculumEvent(sequence = 2) {
  return makeProgressEvent("curriculum_designed", sequence, {
    modules: [
      { id: "m-one", title: "Foundations", kcs: ["comparison", "sorted_order"] },
      { id: "m-two", title: "Search", kcs: ["binary_search"] },
    ],
  });
}

describe("blueprintFromEvents", () => {
  it("is null until a structured graph event arrives (pre-P8 logs, early phases)", () => {
    expect(blueprintFromEvents([makeProgressEvent("concepts_extracted", 0)], false)).toBeNull();
  });

  it("starts every node queued once the graph lands, before any module is authored", () => {
    const state = blueprintFromEvents([graphEvent(), curriculumEvent()], false)!;

    expect(state.goalConcept).toBe("binary_search");
    expect(state.nodeStates.get("comparison")).toBe("queued");
    expect(state.mappedCount).toBe(0);
    expect(state.totalCount).toBe(3);
  });

  it("marks the in-flight module's concepts mapping and authored modules' concepts mapped", () => {
    const events = [
      graphEvent(),
      curriculumEvent(),
      makeProgressEvent("module_authored", 3, { moduleId: "m-one" }),
    ];

    const state = blueprintFromEvents(events, false)!;

    // m-one authored → its KCs mapped; m-two is next in flight → its KCs mapping.
    expect(state.nodeStates.get("comparison")).toBe("mapped");
    expect(state.nodeStates.get("sorted_order")).toBe("mapped");
    expect(state.nodeStates.get("binary_search")).toBe("mapping");
    expect(state.mappedCount).toBe(2);
  });

  it("maps everything once the run completes, whatever the tail events said", () => {
    const state = blueprintFromEvents([graphEvent(), curriculumEvent()], true)!;

    expect(state.nodeStates.get("binary_search")).toBe("mapped");
    expect(state.mappedCount).toBe(3);
  });

  it("renders the graph without state claims when the module mapping is absent", () => {
    // A pre-P8 run log may carry the graph but not the curriculum mapping — nodes render,
    // but no QUEUED/MAPPING/MAPPED is claimed and the counter stays unknown.
    const state = blueprintFromEvents([graphEvent()], false)!;

    expect(state.nodeStates.get("comparison")).toBeNull();
    expect(state.mappedCount).toBeNull();
  });
});
