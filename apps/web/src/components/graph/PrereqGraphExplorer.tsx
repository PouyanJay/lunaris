import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";

import { MOBILE_QUERY, useMediaQuery } from "../../hooks/useMediaQuery";
import { buildGraphLayout, type KcNodeData } from "../../lib/graphLayout";
import type { Course } from "../../types/course";
import { GraphLegend } from "./GraphLegend";
import styles from "./PrereqGraphExplorer.module.css";
import { KcDetailPanel } from "./KcDetailPanel";
import { KcNode } from "./KcNode";

// Defined once, outside render — React Flow warns if nodeTypes is a new object each render.
const NODE_TYPES: NodeTypes = { kc: KcNode };
const FIT_VIEW_OPTIONS = { padding: 0.18, maxZoom: 1.1 };

interface PrereqGraphExplorerProps {
  course: Course;
  /** Drill from the selected concept into the lesson that teaches it (switches to the reader). */
  onOpenLesson?: ((kcId: string) => void) | undefined;
}

/** The interactive prerequisite-graph canvas: a dagre-laid DAG of knowledge components with
 *  flexible bezier prerequisite edges, a difficulty legend, and a docked concept inspector. */
export function PrereqGraphExplorer({ course, onOpenLesson }: PrereqGraphExplorerProps) {
  const layout = useMemo(
    () => buildGraphLayout(course.graph, course.goalConcept),
    [course.graph, course.goalConcept],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [edges, , onEdgesChange] = useEdgesState(layout.edges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // On phones the minimap is noise on a tiny canvas and the legend would collide with the bottom-left
  // zoom controls — drop the minimap and lift the legend to the top-left instead.
  const isMobile = useMediaQuery(MOBILE_QUERY);

  // Re-seed when the course changes (e.g. after a reload). Clearing selectedId here is what
  // keeps the selection-reflection effect below from re-applying a stale selection: by the
  // time it runs after a layout change, selectedId is already null.
  useEffect(() => {
    setNodes(layout.nodes);
    setSelectedId(null);
  }, [layout, setNodes]);

  // Reflect the selection onto React Flow's nodes so the selected node styles itself.
  useEffect(() => {
    setNodes((current) => current.map((node) => ({ ...node, selected: node.id === selectedId })));
  }, [selectedId, setNodes]);

  const onNodeClick = useCallback((_: MouseEvent, node: Node) => setSelectedId(node.id), []);
  const onPaneClick = useCallback(() => setSelectedId(null), []);
  const minimapColor = useCallback(
    (node: Node) => `var(--tier-${(node.data as KcNodeData).tier})`,
    [],
  );

  return (
    <div className={styles.explorer}>
      <div className={styles.canvas} role="application" aria-label="Prerequisite graph canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          colorMode="dark"
          fitView
          fitViewOptions={FIT_VIEW_OPTIONS}
          minZoom={0.4}
          maxZoom={1.75}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--border)" />
          <Controls showInteractive={false} />
          {!isMobile && (
            <MiniMap
              pannable
              zoomable
              nodeColor={minimapColor}
              // React Flow paints the mask into an SVG <path fill>, which can't read a CSS var,
              // so this tracks --bg (#090a0c) as a literal; keep in sync if the page bg changes.
              maskColor="rgba(9, 10, 12, 0.6)"
              className={styles.minimap}
            />
          )}
          <Panel position={isMobile ? "top-left" : "bottom-left"}>
            <GraphLegend />
          </Panel>
        </ReactFlow>
      </div>
      {selectedId && (
        <KcDetailPanel
          course={course}
          selectedId={selectedId}
          onClose={onPaneClick}
          onOpenLesson={onOpenLesson}
        />
      )}
    </div>
  );
}
