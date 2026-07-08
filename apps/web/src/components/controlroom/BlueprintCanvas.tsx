import { Background, BackgroundVariant, Controls, ReactFlow, type NodeTypes } from "@xyflow/react";
import { useMemo } from "react";

import type { BlueprintState } from "../../lib/blueprint";
import { buildGraphLayout, edgeAppearance } from "../../lib/graphLayout";
import { BlueprintNode, type BlueprintFlowNode } from "./BlueprintNode";
import styles from "./BlueprintCanvas.module.css";

// Defined once, outside render — React Flow warns if nodeTypes is a new object each render.
const NODE_TYPES: NodeTypes = { blueprint: BlueprintNode };
const FIT_VIEW_OPTIONS = { padding: 0.18, maxZoom: 1 };

interface BlueprintCanvasProps {
  blueprint: BlueprintState;
}

/** The live prerequisite graph assembling on the blueprint (P8): the Map's dagre geometry with
 *  compact scaffolding nodes; edges glow amber once both endpoints are mapped. Read-only — the
 *  interactive explorer is the ready course's Map tab. */
export function BlueprintCanvas({ blueprint }: BlueprintCanvasProps) {
  const { nodes, edges } = useMemo(() => {
    const layout = buildGraphLayout(blueprint.graph, blueprint.goalConcept ?? "");
    const isMapped = (kcId: string) => blueprint.nodeStates.get(kcId) === "mapped";
    return {
      nodes: layout.nodes.map(
        (node): BlueprintFlowNode => ({
          ...node,
          type: "blueprint",
          draggable: false,
          selectable: false,
          data: { ...node.data, buildState: blueprint.nodeStates.get(node.id) ?? null },
        }),
      ),
      // Assembly lighting, not learner mastery: an edge glows once both endpoints landed.
      edges: layout.edges.map((edge) => ({
        ...edge,
        ...edgeAppearance(isMapped(edge.source) && isMapped(edge.target)),
      })),
    };
  }, [blueprint]);

  return (
    <div className={styles.canvas} role="application" aria-label="Blueprint canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        colorMode="dark"
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
