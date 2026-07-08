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
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";

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

/** A one-shot request to land on the Map with a concept selected (Bookmarks → Map). The seq
 *  gates re-firing — the reader's LessonFocusRequest pattern, pointed the other way. */
export interface MapFocusRequest {
  kc: string;
  seq: number;
}

interface PrereqGraphExplorerProps {
  course: Course;
  /** The learner's live per-KC mastery (P2 snapshot); null while loading / offline — the map
   *  then claims only what the build-time frontier knows (see kcStates). */
  kcMastery?: Record<string, boolean> | null | undefined;
  /** Drill from the selected concept into the lesson that teaches it (switches to the reader). */
  onOpenLesson?: ((kcId: string) => void) | undefined;
  /** Select this concept on arrival (once per request); unknown ids leave the map untouched. */
  focusRequest?: MapFocusRequest | null | undefined;
}

/** The interactive prerequisite-graph canvas: a dagre-laid DAG of knowledge components with
 *  learning-state badges lit by live mastery, amber frontier edges, a difficulty legend, and a
 *  docked concept inspector. */
export function PrereqGraphExplorer({
  course,
  kcMastery,
  onOpenLesson,
  focusRequest,
}: PrereqGraphExplorerProps) {
  const layout = useMemo(
    () => buildGraphLayout(course.graph, course.goalConcept, kcMastery ?? null),
    [course.graph, course.goalConcept, kcMastery],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Render-time mirror so the reseed below can re-apply the selection flag without keying the
  // effect on selectedId (which would re-run it on every click).
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;
  // On phones the minimap is noise on a tiny canvas and the legend would collide with the bottom-left
  // zoom controls — drop the minimap and lift the legend to the top-left instead.
  const isMobile = useMediaQuery(MOBILE_QUERY);

  // Re-seed when the layout changes. A COURSE change (reload) also drops the selection — the
  // selected id may not exist in the new graph; a mastery snapshot landing on the same course
  // only recomputes badges/edge lighting and must NOT close an inspector the learner opened.
  const lastGraph = useRef(course.graph);
  useEffect(() => {
    const courseChanged = lastGraph.current !== course.graph;
    lastGraph.current = course.graph;
    if (courseChanged) selectedIdRef.current = null;
    setNodes(
      layout.nodes.map((node) => ({ ...node, selected: node.id === selectedIdRef.current })),
    );
    setEdges(layout.edges);
    if (courseChanged) setSelectedId(null);
  }, [layout, course.graph, setNodes, setEdges]);

  // Reflect the selection onto React Flow's nodes so the selected node styles itself.
  useEffect(() => {
    setNodes((current) => current.map((node) => ({ ...node, selected: node.id === selectedId })));
  }, [selectedId, setNodes]);

  // Honour a concept drill-in once per request (Bookmarks → Map): select the KC so the inspector
  // opens on arrival. A concept the graph no longer holds (rebuilt course) leaves the map as-is —
  // never a phantom selection. The seq ref gates StrictMode replays and course switches.
  const handledFocusSeq = useRef(0);
  useEffect(() => {
    if (!focusRequest || focusRequest.seq === handledFocusSeq.current) return;
    handledFocusSeq.current = focusRequest.seq;
    if (course.graph.nodes.some((node) => node.id === focusRequest.kc)) {
      setSelectedId(focusRequest.kc);
    }
  }, [focusRequest, course.graph]);

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
