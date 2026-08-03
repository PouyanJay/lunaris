import { authedFetch } from "./apiClient";
import { isConceptGraph, LiveGraphError, type ConceptGraph } from "./liveGraph";
import { readSseFrames } from "./sse";

/** Which part of a cold compile is happening. The copy for each belongs to the surface. */
export type CompilePhase = "decomposing" | "authoring" | "assembling";

/** One beat of a compile in flight: what is happening, and how much of it is done.
 *
 *  `total` is 0 until the concepts are known — a bar that divides by it renders NaN, so every
 *  consumer has to handle the unknown total rather than assuming a denominator. */
export interface CompileProgress {
  phase: CompilePhase;
  done: number;
  total: number;
}

interface StreamGraphOptions {
  /** Called for each compile beat as it arrives. */
  onProgress?: (progress: CompileProgress) => void;
  /** Called once with the run id from the X-Run-Id header, before any frame — a compile that
   *  fails later can then still be named in a support conversation. */
  onRunId?: (runId: string) => void;
  /** Called once with the graph id from the X-Graph-Id header, before any frame — so a stream that
   *  drops mid-compile can re-read the finished graph instead of paying for the compile twice. */
  onGraphId?: (graphId: string) => void;
  /** Abort the in-flight compile (the learner navigates away or names another topic). */
  signal?: AbortSignal;
}

/**
 * Compile `topic` into a concept map, streaming the compile's progress over Server-Sent Events and
 * resolving with the finished map (the terminal `graph` frame).
 *
 * A cold compile runs for minutes, which is why this exists alongside the await-full
 * `POST /api/live/graphs`: it is the only path that can tell a learner what those minutes are being
 * spent on, and it is what the surface uses. Transport,
 * HTTP, mid-stream failure, and "the stream ended without a map" all surface as `LiveGraphError` —
 * one error channel, so the surface has one failure state to render rather than four.
 */
export async function streamGraph(
  apiBaseUrl: string,
  topic: string,
  { onProgress, onRunId, onGraphId, signal }: StreamGraphOptions,
): Promise<ConceptGraph> {
  const url = `${apiBaseUrl}/api/live/graphs/stream?${new URLSearchParams({ topic })}`;
  let response: Response;
  try {
    response = await authedFetch(url, signal ? { signal } : {});
  } catch (cause) {
    throw new LiveGraphError("Could not reach the compiler.", { cause });
  }
  if (!response.ok) {
    throw new LiveGraphError(`Couldn't build the map for this topic (HTTP ${response.status}).`);
  }
  if (!response.body) {
    throw new LiveGraphError("The compile stream returned no body.");
  }

  const runId = response.headers.get("X-Run-Id");
  if (runId) onRunId?.(runId);
  const graphId = response.headers.get("X-Graph-Id");
  if (graphId) onGraphId?.(graphId);

  let graph: ConceptGraph | null = null;
  for await (const frame of readSseFrames(response.body)) {
    if (frame.event === "progress") {
      onProgress?.(frame.data as CompileProgress);
    } else if (frame.event === "error") {
      // The server's own words: it knows whether the topic was unmappable, the compile overran, or
      // its storage is down, and those have different next steps for the learner.
      throw new LiveGraphError(messageOf(frame.data));
    } else if (frame.event === "graph") {
      if (!isConceptGraph(frame.data)) {
        throw new LiveGraphError("Couldn't read the map (unexpected response).");
      }
      graph = frame.data;
    }
  }

  if (!graph) {
    // The body closed before the terminal frame. Reported as a failure rather than as an empty map:
    // an empty map reads to a learner as "this topic has no concepts in it", which is both wrong
    // and gives them no reason to try again.
    throw new LiveGraphError("The compile stopped before the map was ready.");
  }
  return graph;
}

/** The message from an `error` frame, or a fallback if the frame itself was malformed. */
function messageOf(data: unknown): string {
  const message = (data as { message?: unknown } | null)?.message;
  return typeof message === "string" && message ? message : "Couldn't build the map.";
}
