import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import { useEffect, useMemo } from "react";

import { buildVisualLayout, type DiagramNode } from "../../../lib/visualFlowLayout";
import type { FlowSpec, TreeSpec } from "../../../types/course";
import styles from "./FlowDiagram.module.css";

/** A movable diagram node: a hairline panel with the label; edges attach via top/bottom handles. */
function DiagramNodeView({ data }: NodeProps<DiagramNode>) {
  return (
    <div className={styles.node}>
      <Handle type="target" position={Position.Top} />
      {data.label}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

// Defined once outside render — React Flow warns if nodeTypes is a fresh object each render.
const NODE_TYPES: NodeTypes = { diagram: DiagramNodeView };
const FIT_VIEW_OPTIONS = { padding: 0.2, maxZoom: 1.2 };

interface FlowDiagramProps {
  spec: FlowSpec | TreeSpec;
}

/** Branded interactive canvas for flow + tree specs: dagre-laid, movable nodes with flexible bezier
 *  connectors, themed onto the design tokens. */
export function FlowDiagram({ spec }: FlowDiagramProps) {
  const layout = useMemo(() => buildVisualLayout(spec), [spec]);
  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);

  // Re-seed when the spec changes (e.g. a different lesson's diagram).
  useEffect(() => {
    setNodes(layout.nodes);
    setEdges(layout.edges);
  }, [layout, setNodes, setEdges]);

  return (
    <div className={styles.canvas} role="application" aria-label={spec.title ?? "Diagram"}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        colorMode="dark"
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={0.3}
        maxZoom={2}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
