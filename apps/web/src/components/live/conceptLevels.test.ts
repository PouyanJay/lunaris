import { describe, expect, it } from "vitest";

import { conceptLevels } from "./conceptLevels";
import type { ConceptGraph, ConceptNode } from "../../lib/liveGraph";

function node(id: string, requires: string[] = []): ConceptNode {
  return {
    id,
    name: id.toUpperCase(),
    definition: `${id} defined.`,
    requires,
    provenance: "compiled",
    aliases: [],
    teachingSpec: null,
    masteryCriteria: [],
  };
}

function graph(nodes: ConceptNode[], topoOrder: string[]): ConceptGraph {
  return { graphId: "g1", topic: "T", version: 1, nodes, topoOrder, isAcyclic: true };
}

describe("conceptLevels", () => {
  it("puts everything that needs nothing on the first level", () => {
    const levels = conceptLevels(graph([node("a"), node("b"), node("c", ["a"])], ["a", "b", "c"]));

    expect(levels[0]?.depth).toBe(1);
    expect(levels[0]?.concepts.map((concept) => concept.id)).toEqual(["a", "b"]);
  });

  it("places a concept below the deepest thing it needs, not the first", () => {
    // c needs a (level 1) and b (level 2), so it cannot sit alongside b.
    const levels = conceptLevels(
      graph([node("a"), node("b", ["a"]), node("c", ["a", "b"])], ["a", "b", "c"]),
    );

    expect(levels.map((level) => level.concepts.map((concept) => concept.id))).toEqual([
      ["a"],
      ["b"],
      ["c"],
    ]);
  });

  it("keeps a concept the server left out of the order rather than dropping it off the map", () => {
    // A map missing a concept it compiled is worse than one ordered imperfectly.
    const levels = conceptLevels(graph([node("a"), node("orphan")], ["a"]));

    const placed = levels.flatMap((level) => level.concepts.map((concept) => concept.id));
    expect(placed).toContain("orphan");
  });

  it("is empty for a map with no concepts, rather than inventing a level", () => {
    expect(conceptLevels(graph([], []))).toEqual([]);
  });
});
