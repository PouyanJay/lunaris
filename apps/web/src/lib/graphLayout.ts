import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { KnowledgeComponent, PrerequisiteGraph } from "../types/course";

/** Data carried by each KC node. Indexed signature satisfies React Flow v12's node-data
 *  constraint (`Record<string, unknown>`) while keeping the named fields typed. */
export interface KcNodeData extends Record<string, unknown> {
  kc: KnowledgeComponent;
  /** Difficulty tier 1..5, driving the node's accent on the difficulty ramp. */
  tier: number;
  /** 1-based position in the topological learning order (0 if absent). */
  order: number;
  /** The course goal KC — the destination of the path. */
  isGoal: boolean;
  /** Already on the learner's frontier (known); de-emphasised. */
  isKnown: boolean;
}

export type KcNode = Node<KcNodeData, "kc">;

export const NODE_WIDTH = 232;
export const NODE_HEIGHT = 92;

/** Number of difficulty tiers on the ramp (1..N). */
export const DIFFICULTY_TIER_COUNT = 5;
/** Sentinel for a KC absent from the topological order. */
export const UNKNOWN_ORDER = 0;

// dagre tuning — the gaps that make the DAG read as a foundations→goal learning path.
const NODE_SEP = 56; // horizontal gap between sibling concepts
const RANK_SEP = 72; // vertical gap between prerequisite levels
const GRAPH_MARGIN = 32; // canvas inset on all sides

/** Map a 0..1 difficulty onto a 1..DIFFICULTY_TIER_COUNT tier (clamped). */
export function difficultyTier(difficulty: number): number {
  const clamped = Math.max(0, Math.min(1, difficulty));
  return Math.min(DIFFICULTY_TIER_COUNT, Math.floor(clamped * DIFFICULTY_TIER_COUNT) + 1);
}

/** 1-based position of a KC in the learning order, or UNKNOWN_ORDER if it isn't in it. */
export function orderInPath(topoOrder: string[], kcId: string): number {
  return topoOrder.indexOf(kcId) + 1;
}

/**
 * Lay the prerequisite DAG out top-to-bottom with dagre: prerequisites rank above the
 * concepts that depend on them, so the canvas reads as a learning path from foundations
 * down to the goal. Returns React Flow nodes (absolute positions) and bezier edges.
 */
export function buildGraphLayout(
  graph: PrerequisiteGraph,
  goalConcept: string,
): { nodes: KcNode[]; edges: Edge[] } {
  const dag = new dagre.graphlib.Graph();
  dag.setDefaultEdgeLabel(() => ({}));
  dag.setGraph({
    rankdir: "TB",
    nodesep: NODE_SEP,
    ranksep: RANK_SEP,
    marginx: GRAPH_MARGIN,
    marginy: GRAPH_MARGIN,
  });

  for (const kc of graph.nodes) {
    dag.setNode(kc.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of graph.edges) {
    if (dag.hasNode(edge.from) && dag.hasNode(edge.to)) {
      dag.setEdge(edge.from, edge.to);
    }
  }
  dagre.layout(dag);

  const frontier = new Set(graph.frontier);

  const nodes: KcNode[] = graph.nodes.map((kc) => {
    const point = dag.node(kc.id);
    return {
      id: kc.id,
      type: "kc",
      position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 },
      data: {
        kc,
        tier: difficultyTier(kc.difficulty),
        order: orderInPath(graph.topoOrder, kc.id),
        isGoal: kc.id === goalConcept,
        isKnown: frontier.has(kc.id),
      },
    };
  });

  const nodeIds = new Set(graph.nodes.map((kc) => kc.id));
  const edges: Edge[] = graph.edges
    .filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to))
    .map((edge) => ({
      id: `${edge.from}->${edge.to}`,
      source: edge.from,
      target: edge.to,
      // Flexible bezier connector; the arrowhead points prerequisite → dependent.
      type: "default",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: "var(--border-strong)",
      },
      data: { strength: edge.strength },
    }));

  return { nodes, edges };
}
