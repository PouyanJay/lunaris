import type { PrerequisiteGraph } from "../types/course";

/** A knowledge component's learning state on the Map: mastered (build-time frontier or every
 *  objective understood), up_next (unmastered, all prerequisites mastered — the learnable
 *  frontier), or locked (an unmastered prerequisite remains). */
export type KcState = "mastered" | "up_next" | "locked";

/**
 * Derive each KC's state from the graph and the learner's mastery. The mastered set is the
 * build-time `frontier` (what the learner already knew — static truth, available offline) plus
 * the live `kcMastery` snapshot (P2's all-objectives-per-KC rollup). With no snapshot
 * (`kcMastery` null — offline or still loading), up_next/locked are statements about a learner
 * we can't see: those KCs map to `null` and render no state badge.
 */
export function kcStates(
  graph: PrerequisiteGraph,
  kcMastery: Record<string, boolean> | null,
): ReadonlyMap<string, KcState | null> {
  const mastered = new Set(graph.frontier);
  for (const [kcId, isMastered] of Object.entries(kcMastery ?? {})) {
    if (isMastered) mastered.add(kcId);
  }

  const prerequisitesOf = new Map<string, string[]>();
  for (const edge of graph.edges) {
    const existing = prerequisitesOf.get(edge.to);
    if (existing) existing.push(edge.from);
    else prerequisitesOf.set(edge.to, [edge.from]);
  }

  const states = new Map<string, KcState | null>();
  for (const node of graph.nodes) {
    if (mastered.has(node.id)) {
      states.set(node.id, "mastered");
    } else if (kcMastery === null) {
      states.set(node.id, null);
    } else {
      const prerequisites = prerequisitesOf.get(node.id) ?? [];
      const unlocked = prerequisites.every((prerequisite) => mastered.has(prerequisite));
      states.set(node.id, unlocked ? "up_next" : "locked");
    }
  }
  return states;
}
