import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import { kcStates, type KcState } from "./kcStates";
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
  /** Learning state from the frontier + live mastery; null when unknowable (see kcStates). */
  state: KcState | null;
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
  kcMastery: Record<string, boolean> | null = null,
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

  const states = kcStates(graph, kcMastery);

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
        state: states.get(kc.id) ?? null,
      },
    };
  });

  // An edge lights amber when both endpoints are on the learner's active path (mastered or up
  // next) — the design's lit-frontier treatment; everything else stays a dim hairline.
  const isLit = (kcId: string): boolean => {
    const state = states.get(kcId);
    return state === "mastered" || state === "up_next";
  };

  const nodeIds = new Set(graph.nodes.map((kc) => kc.id));
  const edges: Edge[] = graph.edges
    .filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to))
    .map((edge) => {
      const lit = isLit(edge.from) && isLit(edge.to);
      return {
        id: `${edge.from}->${edge.to}`,
        source: edge.from,
        target: edge.to,
        // Flexible bezier connector; the arrowhead points prerequisite → dependent.
        type: "default",
        className: lit ? "edge-lit" : "edge-dim",
        style: lit
          ? { stroke: "var(--accent-500)", strokeOpacity: 0.4, strokeWidth: 1.4 }
          : { stroke: "var(--border-strong)", strokeOpacity: 0.6, strokeWidth: 1.2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: lit ? "var(--accent-500)" : "var(--border-strong)",
        },
        data: { strength: edge.strength },
      };
    });

  return { nodes, edges };
}
