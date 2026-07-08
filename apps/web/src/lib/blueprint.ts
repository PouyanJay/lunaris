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

/** Structure without a mapping (pre-P8 logs): render nodes, claim no states — unless the run is
 *  complete, where "everything mapped" is a fact of the published course. */
function nodeStatesWithoutMapping(
  graph: PrerequisiteGraph,
  complete: boolean,
): Map<string, BlueprintNodeState | null> {
  const states = new Map<string, BlueprintNodeState | null>();
  for (const node of graph.nodes) states.set(node.id, complete ? "mapped" : null);
  return states;
}

/** Full assembly derivation: authored modules' concepts are mapped; the next unauthored module's
 *  concepts pulse as mapping while authoring is underway (stages emit at COMPLETION, so the
 *  window opens when discovery finished and runs through the authored/verified alternation);
 *  everything else is queued. */
function nodeStatesFromModules(
  graph: PrerequisiteGraph,
  modules: CurriculumModuleMap[],
  events: ProgressEvent[],
  complete: boolean,
): Map<string, BlueprintNodeState | null> {
  const authored = new Set(
    events
      .filter((event) => event.stage === "module_authored" && event.moduleId)
      .map((event) => event.moduleId as string),
  );
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
    for (const kc of module.kcs) {
      if (complete || authored.has(module.id)) mapped.add(kc);
      else if (module === inFlight) mapping.add(kc);
    }
  }

  const states = new Map<string, BlueprintNodeState | null>();
  for (const node of graph.nodes) {
    states.set(
      node.id,
      complete || mapped.has(node.id) ? "mapped" : mapping.has(node.id) ? "mapping" : "queued",
    );
  }
  return states;
}

/**
 * Fold the progress stream into the blueprint's assembly state (P8). The graph structure and the
 * module → KC mapping ride GRAPH_BUILT / CURRICULUM_DESIGNED (T1). Returns null until a
 * structured graph event exists (early phases, pre-P8 logs): no structure, no blueprint — the
 * canvas falls back rather than faking nodes.
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

  const modules = latestWith(events, (event) =>
    event.stage === "curriculum_designed" && event.modules?.length ? event.modules : null,
  );

  const nodeStates =
    modules === null
      ? nodeStatesWithoutMapping(graph, complete)
      : nodeStatesFromModules(graph, modules, events, complete);
  const mappedCount =
    modules === null && !complete
      ? null
      : [...nodeStates.values()].filter((state) => state === "mapped").length;

  return {
    graph,
    goalConcept: graphEvent.goalConcept ?? null,
    nodeStates,
    mappedCount,
    totalCount: graph.nodes.length,
  };
}
