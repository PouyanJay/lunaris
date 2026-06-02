import type {
  AgentEvent,
  AgentEventKind,
  Claim,
  Course,
  CourseRun,
  GagneFlags,
  Lesson,
  Module,
  ProgressEvent,
  ProgressStage,
  RunEvent,
  Segment,
} from "../types/course";

const NO_GAGNE: GagneFlags = {
  gainAttention: false,
  stateObjective: false,
  recallPrior: false,
  presentContent: false,
  guideLearning: false,
  elicitPerformance: false,
  provideFeedback: false,
  assessPerformance: false,
  enhanceTransfer: false,
};

function segment(prose: string, claims: Claim[] = []): Segment {
  return { prose, visuals: [], claims };
}

/** A complete Merrill lesson for reader tests: four phases with distinct prose, a grounded claim in
 *  the demonstrate phase (cites `src-1`), so the reader has real content to render. */
export function makeLesson(overrides: Partial<Lesson> = {}): Lesson {
  return {
    id: "m-binary_search-l0",
    segments: {
      activate: segment("Recall how you find a word in a dictionary by halving the pages."),
      demonstrate: segment("Binary search halves the candidate range on each comparison.", [
        {
          text: "Comparison reduces the problem size each step.",
          supportedBy: "src-1",
          verifierStatus: "supported",
        },
      ]),
      apply: segment("Trace binary search on [1, 3, 5, 7, 9] searching for 7."),
      integrate: segment("Where else does halving a search space speed things up?"),
    },
    gagne: { ...NO_GAGNE },
    loadEstimate: 1.0,
    ...overrides,
  };
}

/** A course module with sensible defaults — pass `lessons`/`title` to build multi-lesson courses
 *  for reader navigation tests. */
export function makeModule(overrides: Partial<Module> = {}): Module {
  return {
    id: "m-test",
    title: "Module",
    kcs: [],
    objectives: [],
    lessons: [makeLesson()],
    assessment: { items: [] },
    difficultyIndex: 0.5,
    ...overrides,
  };
}

/** A run-history row for sidebar tests; mirrors the camelCase CourseRun wire shape. */
export function makeRun(overrides: Partial<CourseRun> = {}): CourseRun {
  return {
    id: "course-test",
    runId: "run-test",
    topic: "How binary search works",
    status: "completed",
    kcCount: 3,
    moduleCount: 1,
    createdAt: "2026-05-31T09:00:00Z",
    updatedAt: "2026-05-31T09:01:00Z",
    ...overrides,
  };
}

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
        objectives: [
          {
            statement: "Given a sorted array, locate a target with binary search.",
            bloomLevel: "apply",
            kc: "binary_search",
            assessedBy: ["m0-i0"],
          },
        ],
        lessons: [makeLesson()],
        assessment: {
          items: [
            {
              id: "m0-i0",
              prompt: "What is the worst-case time complexity of binary search?",
              objective: "binary_search",
              answer: "O(log n)",
            },
          ],
        },
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

/** A fetch-style Response whose body streams the given SSE text frames. Pass `open: true` to leave
 *  the stream un-closed (it stays "streaming" — for asserting the live transcript mid-build). */
export function sseStreamResponse(
  frames: string[],
  init: { ok?: boolean; status?: number; open?: boolean } = {},
) {
  const { ok = true, status = 200, open = false } = init;
  return {
    ok,
    status,
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        if (!open) controller.close();
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

/** A fine-grained agent-transcript event with null defaults; set the fields the `kind` uses. */
export function makeAgentEvent(
  kind: AgentEventKind,
  sequence: number,
  extra: Partial<AgentEvent> = {},
): AgentEvent {
  return {
    kind,
    runId: "run-test",
    sequence,
    stage: null,
    text: null,
    delta: null,
    tool: null,
    toolArgs: null,
    result: null,
    todos: null,
    ...extra,
  };
}

export function agentFrame(
  kind: AgentEventKind,
  sequence: number,
  extra: Partial<AgentEvent> = {},
): string {
  return `event: agent\ndata: ${JSON.stringify(makeAgentEvent(kind, sequence, extra))}\n\n`;
}

/** A persisted run-event row (the GET /api/runs/{runId}/events wire shape) wrapping a payload. */
export function makeRunEvent(
  seq: number,
  payload: ProgressEvent | AgentEvent,
  extra: Partial<Omit<RunEvent, "seq" | "payload">> = {},
): RunEvent {
  const kind: RunEvent["kind"] = "kind" in payload ? "agent" : "progress";
  return { runId: "run-test", courseId: "course-test", seq, kind, payload, ...extra };
}
