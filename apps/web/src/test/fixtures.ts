import type { Course, ProgressEvent, ProgressStage } from "../types/course";

/** A small but complete course-object for tests: comparison → sorted_order → binary_search,
 *  with binary_search the goal. Mirrors the real (camelCase) schema shape. */
export function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "course-test",
    topic: "How binary search works",
    goalConcept: "binary_search",
    status: "review",
    provenance: [{ id: "src-1", title: "CLRS", url: "https://example.org/clrs", snippet: "…" }],
    modules: [
      {
        id: "m-binary_search",
        title: "Binary Search",
        kcs: ["binary_search"],
        objectives: [],
        difficultyIndex: 0.75,
      },
    ],
    graph: {
      nodes: [
        {
          id: "comparison",
          label: "Comparison",
          definition: "Ordering two values.",
          difficulty: 0.1,
          bloomCeiling: "apply",
          sources: [],
        },
        {
          id: "sorted_order",
          label: "Sorted Order",
          definition: "Elements arranged by a key.",
          difficulty: 0.45,
          bloomCeiling: "understand",
          sources: [],
        },
        {
          id: "binary_search",
          label: "Binary Search",
          definition: "Halving a sorted range each step.",
          difficulty: 0.75,
          bloomCeiling: "apply",
          sources: ["src-1"],
        },
      ],
      edges: [
        { from: "comparison", to: "sorted_order", strength: 0.9 },
        { from: "sorted_order", to: "binary_search", strength: 0.8 },
      ],
      frontier: [],
      isAcyclic: true,
      topoOrder: ["comparison", "sorted_order", "binary_search"],
    },
    ...overrides,
  };
}

/** A ProgressEvent with sensible null defaults; pass `extra` to set the stage's counts. */
export function makeProgressEvent(
  stage: ProgressStage,
  sequence: number,
  extra: Partial<ProgressEvent> = {},
): ProgressEvent {
  return {
    stage,
    label: `${stage} step`,
    runId: "run-test",
    sequence,
    kcCount: null,
    edgeCount: null,
    moduleCount: null,
    moduleId: null,
    claimsTotal: null,
    claimsSupported: null,
    claimsCut: null,
    status: null,
    ...extra,
  };
}

/** A fetch-style Response whose body streams the given SSE text frames. */
export function sseStreamResponse(frames: string[], init: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = init;
  return {
    ok,
    status,
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    }),
  };
}

export function progressFrame(
  stage: ProgressStage,
  sequence: number,
  extra: Partial<ProgressEvent> = {},
): string {
  return `event: progress\ndata: ${JSON.stringify(makeProgressEvent(stage, sequence, extra))}\n\n`;
}

export function courseFrame(course: Course = makeCourse()): string {
  return `event: course\ndata: ${JSON.stringify(course)}\n\n`;
}
