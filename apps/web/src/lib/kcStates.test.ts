import { describe, expect, it } from "vitest";

import { kcStates } from "./kcStates";
import type { PrerequisiteGraph } from "../types/course";

/** comparison → sorted_order → binary_search, plus a parallel foundation "arrays". */
function graph(frontier: string[] = []): PrerequisiteGraph {
  const node = (id: string) => ({
    id,
    label: id,
    definition: "",
    difficulty: 0.5,
    bloomCeiling: "apply" as const,
    sources: [],
  });
  return {
    nodes: [node("comparison"), node("sorted_order"), node("binary_search"), node("arrays")],
    edges: [
      { from: "comparison", to: "sorted_order", strength: 0.9 },
      { from: "sorted_order", to: "binary_search", strength: 0.8 },
      { from: "arrays", to: "binary_search", strength: 0.7 },
    ],
    frontier,
    isAcyclic: true,
    topoOrder: ["comparison", "arrays", "sorted_order", "binary_search"],
  };
}

describe("kcStates", () => {
  it("derives mastered / up_next / locked from the mastery set and prerequisites", () => {
    const states = kcStates(graph(), { comparison: true });

    expect(states.get("comparison")).toBe("mastered");
    // Its only prerequisite is mastered — the frontier of learning.
    expect(states.get("sorted_order")).toBe("up_next");
    // arrays (unmastered, no prerequisites) is also immediately learnable.
    expect(states.get("arrays")).toBe("up_next");
    // binary_search still has unmastered prerequisites on both paths.
    expect(states.get("binary_search")).toBe("locked");
  });

  it("counts the build-time frontier as mastered alongside live mastery", () => {
    const states = kcStates(graph(["comparison"]), { sorted_order: true });

    expect(states.get("comparison")).toBe("mastered");
    expect(states.get("sorted_order")).toBe("mastered");
    // Both binary_search prerequisites: sorted_order mastered, arrays not → locked.
    expect(states.get("binary_search")).toBe("locked");
  });

  it("ignores false entries in the mastery record", () => {
    const states = kcStates(graph(), { comparison: false });

    expect(states.get("comparison")).toBe("up_next");
  });

  it("without a snapshot, only frontier mastery is knowable — everything else is null", () => {
    // Honesty rule: up_next/locked are statements about the learner; offline we can't make them.
    const states = kcStates(graph(["comparison"]), null);

    expect(states.get("comparison")).toBe("mastered");
    expect(states.get("sorted_order")).toBeNull();
    expect(states.get("binary_search")).toBeNull();
    expect(states.get("arrays")).toBeNull();
  });
});
