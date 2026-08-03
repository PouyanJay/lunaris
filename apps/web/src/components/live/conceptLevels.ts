import type { ConceptGraph, ConceptNode } from "../../lib/liveGraph";

/** One rank of the map: the concepts that become learnable at the same point. */
export interface ConceptLevel {
  /** 1-based depth — level 1 needs nothing, level 2 needs only level 1, and so on. */
  depth: number;
  concepts: ConceptNode[];
}

/**
 * Group a compiled map into prerequisite levels.
 *
 * A flat list in topological order is *an* honest rendering of a DAG, but it hides the thing the
 * map exists to show: that several concepts are ready at once, and that depth is what a learner is
 * actually climbing. A concept sits one level below the deepest thing it needs, so everything on a
 * level can be taken in any order — which is exactly the freedom Phase 2's director trades on.
 *
 * Nodes the server left out of `topoOrder` are still placed rather than dropped: a map missing a
 * concept it compiled is worse than one whose ordering is imperfect.
 */
export function conceptLevels(graph: ConceptGraph): ConceptLevel[] {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  // Walk in the server's derived order so a concept's prerequisites are always already placed;
  // anything absent from that order is appended, keeping every compiled concept on the map.
  const inOrder = new Set(graph.topoOrder);
  const ordered = [
    ...graph.topoOrder.map((id) => byId.get(id)).filter((node) => node !== undefined),
    ...graph.nodes.filter((node) => !inOrder.has(node.id)),
  ];

  const depths = new Map<string, number>();
  for (const node of ordered) {
    const deepestPrerequisite = node.requires.reduce(
      (deepest, id) => Math.max(deepest, depths.get(id) ?? 0),
      0,
    );
    depths.set(node.id, deepestPrerequisite + 1);
  }

  const levels = new Map<number, ConceptNode[]>();
  for (const node of ordered) {
    const depth = depths.get(node.id) ?? 1;
    levels.set(depth, [...(levels.get(depth) ?? []), node]);
  }

  return [...levels.entries()]
    .sort(([left], [right]) => left - right)
    .map(([depth, concepts]) => ({ depth, concepts }));
}
