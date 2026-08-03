import { authedFetch } from "./apiClient";

/** Where a concept came from — a cold compile, or a learner's mid-session request (C1). */
export type NodeProvenance = "compiled" | "extended";

/** One atomic concept: the unit a Live session teaches and assesses. */
export interface ConceptNode {
  id: string;
  name: string;
  definition: string;
  /** Ids of the concepts that must be understood before this one. */
  requires: string[];
  provenance: NodeProvenance;
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
