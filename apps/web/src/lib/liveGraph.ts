import { authedFetch } from "./apiClient";

/** Where a concept came from — a cold compile, or a learner's mid-session request (C1). */
export type NodeProvenance = "compiled" | "extended";

/** The shape of evidence a mastery criterion asks for. Each maps to something the runtime can
 *  stage: a checkable question, a simulator milestone, or teaching it back. */
export type MasteryCriterionKind = "predict" | "manipulate" | "explain";

/** One thing the learner must be able to DO to have understood a concept — never "knows that…",
 *  because a statement of knowledge cannot be watched and a statement of action can. */
export interface MasteryCriterion {
  kind: MasteryCriterionKind;
  statement: string;
  /** Demonstrating this needs an interactive simulator (Phase 3). */
  needsSim: boolean;
}

/** How a concept should be taught. `misconceptions` are stated as the learner would believe them,
 *  not as corrections — that is what lets a tutor go looking for the wrong model in front of it. */
export interface TeachingSpec {
  objective: string;
  misconceptions: string[];
  depth: "intuition_first" | "formal" | "applied";
}

/** One atomic concept: the unit a Live session teaches and assesses.
 *
 *  `teachingSpec` is null when authoring failed for this concept: it is still a real concept, and
 *  the compiler deliberately keeps it rather than losing the map over one failed call. */
export interface ConceptNode {
  id: string;
  name: string;
  definition: string;
  /** Ids of the concepts that must be understood before this one. */
  requires: string[];
  provenance: NodeProvenance;
  /** Other names a learner might call this by — always an array, empty when the name stands alone. */
  aliases: string[];
  /** Always present on the wire, but null when authoring failed for this concept. */
  teachingSpec: TeachingSpec | null;
  /** Always an array — empty when this concept has none yet, never absent. */
  masteryCriteria: MasteryCriterion[];
}

/** A topic's concept map. `topoOrder` and `isAcyclic` are derived server-side by assembly — the
 *  compiler never asserts its own correctness — so the map can render them as fact. */
export interface ConceptGraph {
  graphId: string;
  topic: string;
  version: number;
  nodes: ConceptNode[];
  topoOrder: string[];
  isAcyclic: boolean;
}

export class LiveGraphError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "LiveGraphError";
  }
}

/** Compile a topic into a concept map.
 *
 *  Rejects with `LiveGraphError` on transport/HTTP failure and on an alien payload shape — the map
 *  reads node fields unguarded, so the trust-boundary check belongs here rather than in the view. */
export async function compileGraph(
  apiBaseUrl: string,
  topic: string,
  signal?: AbortSignal,
): Promise<ConceptGraph> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/live/graphs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic }),
      ...(signal ? { signal } : {}),
    });
  } catch (cause) {
    throw new LiveGraphError("Could not reach the compiler.", { cause });
  }
  if (!response.ok) {
    throw new LiveGraphError(`Couldn't build the map for this topic (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as ConceptGraph | null;
  if (!isConceptGraph(body)) {
    throw new LiveGraphError("Couldn't read the map (unexpected response).");
  }
  return body;
}

/** Every field the map reads, checked here so the view never has to.
 *
 *  `topoOrder` earns its place in particular: `ConceptMap` maps over it directly, so a payload
 *  missing it would throw a raw TypeError inside render rather than surfacing as the recoverable
 *  `LiveGraphError` this boundary promises. */
function isConceptGraph(body: ConceptGraph | null): body is ConceptGraph {
  return (
    !!body &&
    typeof body.graphId === "string" &&
    typeof body.topic === "string" &&
    typeof body.version === "number" &&
    typeof body.isAcyclic === "boolean" &&
    Array.isArray(body.topoOrder) &&
    body.topoOrder.every((id) => typeof id === "string") &&
    Array.isArray(body.nodes) &&
    body.nodes.every(
      (node) =>
        typeof node?.id === "string" &&
        typeof node?.name === "string" &&
        typeof node?.definition === "string" &&
        Array.isArray(node?.requires),
    )
  );
}
