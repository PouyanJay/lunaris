import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { FlowSpec, TreeSpec } from "../types/course";

/** Data carried by a diagram node. The indexed signature satisfies React Flow v12's node-data
 *  constraint while keeping `label` typed. */
export interface DiagramNodeData extends Record<string, unknown> {
  label: string;
}

export type DiagramNode = Node<DiagramNodeData, "diagram">;

const NODE_WIDTH = 168;
const NODE_HEIGHT = 44;
const NODE_SEP = 40;
const RANK_SEP = 56;
const GRAPH_MARGIN = 24;

/** Lay a flow or tree spec out top-to-bottom with dagre into React Flow nodes (movable, absolute
 *  positions) and bezier edges. A tree's edges are derived from each node's `parentId`. */
export function buildVisualLayout(spec: FlowSpec | TreeSpec): {
  nodes: DiagramNode[];
  edges: Edge[];
} {
  const nodeIds = new Set(spec.nodes.map((node) => node.id));
  const rawEdges = (
    spec.type === "flow"
      ? spec.edges.map((edge) => ({ from: edge.from, to: edge.to, label: edge.label }))
      : spec.nodes
          .filter((node) => node.parentId !== null)
          .map((node) => ({ from: node.parentId as string, to: node.id, label: null }))
  ).filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to));

  const dag = new dagre.graphlib.Graph();
  dag.setDefaultEdgeLabel(() => ({}));
  dag.setGraph({
    rankdir: "TB",
    nodesep: NODE_SEP,
    ranksep: RANK_SEP,
    marginx: GRAPH_MARGIN,
    marginy: GRAPH_MARGIN,
  });

  for (const node of spec.nodes) dag.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of rawEdges) dag.setEdge(edge.from, edge.to);
  dagre.layout(dag);

  const nodes: DiagramNode[] = spec.nodes.map((node) => {
    const point = dag.node(node.id);
    return {
      id: node.id,
      type: "diagram",
      position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 },
      data: { label: node.label },
    };
  });

  const edges: Edge[] = rawEdges.map((edge, index) => ({
    id: `${edge.from}->${edge.to}-${index}`,
    source: edge.from,
    target: edge.to,
    label: edge.label ?? undefined,
    type: "default",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 12,
      height: 12,
      color: "var(--border-strong)",
    },
  }));

  return { nodes, edges };
}
