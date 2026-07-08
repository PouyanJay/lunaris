import type { CurriculumModuleMap, PrerequisiteGraph, ProgressEvent } from "../types/course";

/** A concept's assembly state on the live blueprint: queued (placed, waiting), mapping (its
 *  module is being authored), mapped (its module landed). Null when the run log carries the
 *  graph but no module mapping (pre-P8 logs) — the node renders without a state claim. */
export type BlueprintNodeState = "queued" | "mapping" | "mapped";

export interface BlueprintState {
  graph: PrerequisiteGraph;
  goalConcept: string | null;
  nodeStates: ReadonlyMap<string, BlueprintNodeState | null>;
  /** Distinct mapped concepts, or null when no module mapping streamed (counter unknowable). */
  mappedCount: number | null;
  totalCount: number;
}

function latestWith<T>(
  events: ProgressEvent[],
  pick: (event: ProgressEvent) => T | null | undefined,
): T | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const value = pick(events[i]!);
    if (value != null) return value;
  }
  return null;
}

/**
 * Fold the progress stream into the blueprint's assembly state (P8). The graph structure and the
 * module → KC mapping ride GRAPH_BUILT / CURRICULUM_DESIGNED (T1); each MODULE_AUTHORED event
 * lights its module's concepts as mapped, and the next unauthored module's concepts pulse as
 * mapping. `complete` maps everything — a published course has nothing left in flight. Returns
 * null until a structured graph event exists (early phases, pre-P8 logs): no structure, no
 * blueprint — the canvas falls back rather than faking nodes.
 */
export function blueprintFromEvents(
  events: ProgressEvent[],
  complete: boolean,
): BlueprintState | null {
  const graphEvent = latestWith(events, (event) =>
    event.stage === "graph_built" && event.graph ? event : null,
  );
  if (!graphEvent?.graph) return null;
  const graph = graphEvent.graph;

  const modules: CurriculumModuleMap[] | null = latestWith(events, (event) =>
    event.stage === "curriculum_designed" && event.modules?.length ? event.modules : null,
  );

  const nodeStates = new Map<string, BlueprintNodeState | null>();
  let mappedCount: number | null = null;

  if (modules === null) {
    // Structure without a mapping: render nodes, claim no states (strapline honesty) — unless
    // the run is complete, where "everything mapped" is a fact of the published course.
    for (const node of graph.nodes) nodeStates.set(node.id, complete ? "mapped" : null);
    mappedCount = complete ? graph.nodes.length : null;
  } else {
    const authored = new Set(
      events
        .filter((event) => event.stage === "module_authored" && event.moduleId)
        .map((event) => event.moduleId as string),
    );
    // Stages emit at COMPLETION, so authoring is underway from the moment discovery finished
    // through the per-module authored/verified alternation. Outside that window (curriculum just
    // designed, grounding still running, resources onward) nothing is actively mapping.
    const lastStage = events.at(-1)?.stage ?? null;
    const authoringUnderway =
      lastStage === "grounding_discovered" ||
      lastStage === "module_authored" ||
      lastStage === "claims_verified";
    const inFlight =
      complete || !authoringUnderway ? null : modules.find((module) => !authored.has(module.id));

    const mapped = new Set<string>();
    const mapping = new Set<string>();
    for (const module of modules) {
      const target = complete || authored.has(module.id) ? mapped : null;
      for (const kc of module.kcs) {
        if (target) mapped.add(kc);
        else if (module === inFlight) mapping.add(kc);
      }
    }
    for (const node of graph.nodes) {
      nodeStates.set(
        node.id,
        complete || mapped.has(node.id)
          ? "mapped"
          : mapping.has(node.id)
            ? "mapping"
            : "queued",
      );
    }
    mappedCount = [...nodeStates.values()].filter((state) => state === "mapped").length;
  }

  return {
    graph,
    goalConcept: graphEvent.goalConcept ?? null,
    nodeStates,
    mappedCount,
    totalCount: graph.nodes.length,
  };
}
