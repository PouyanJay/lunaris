import { vi } from "vitest";

import { type BriefResponse, QUESTION_IDS } from "../types/clarifier";
import type {
  AgentEvent,
  AgentEventKind,
  Citation,
  Claim,
  Course,
  CourseRun,
  CourseSummary,
  GagneFlags,
  Lesson,
  Module,
  ProgressEvent,
  ProgressStage,
  Resource,
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

function segment(prose: string, claims: Claim[] = [], resources: Resource[] = []): Segment {
  return { prose, visuals: [], claims, resources };
}

/** A grounding citation with its trust/provenance set, for reader tests (P6.0). Defaults to a
 *  classified, high-credibility source; pass `trustTier: undefined` to model a pre-P6.0 citation. */
export function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    id: "src-1",
    title: "CLRS",
    url: "https://example.org/clrs",
    snippet: "Comparison halves the search range.",
    trustTier: "reputable",
    credibility: 0.91,
    sourceType: "reference",
    fetchedAt: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

/** A vetted resource with sensible defaults for reader/transcript tests. */
export function makeResource(overrides: Partial<Resource> = {}): Resource {
  return {
    kind: "video",
    title: "Binary search visualised",
    url: "https://www.youtube.com/watch?v=demo",
    source: "youtube.com",
    why: "A 6-min animation of halving the search range.",
    trustTier: "open",
    credibility: 0.8,
    fetchedAt: "2026-06-03T00:00:00Z",
    duration: "6:12",
    author: "CS Dojo",
    ...overrides,
  };
}

/** A complete Merrill lesson for reader tests: four phases with distinct prose, a grounded claim in
 *  the demonstrate phase (cites `src-1`), so the reader has real content to render. */
export function makeLesson(overrides: Partial<Lesson> = {}): Lesson {
  return {
    id: "m-binary_search-l0",
    segments: {
      activate: segment("Recall how you find a word in a dictionary by halving the pages."),
      demonstrate: segment(
        "Binary search halves the candidate range on each comparison.",
        [
          {
            text: "Comparison reduces the problem size each step.",
            supportedBy: "src-1",
            verifierStatus: "supported",
          },
        ],
        [makeResource()],
      ),
      apply: segment("Trace binary search on [1, 3, 5, 7, 9] searching for 7."),
      integrate: segment("Where else does halving a search space speed things up?"),
    },
    expects: ["You can compare two numbers and recognise a sorted list."],
    selfCheck: ["Can you locate 7 in a 9-element sorted array in at most 4 comparisons?"],
    gagne: { ...NO_GAGNE },
    loadEstimate: 1.0,
    ...overrides,
  };
}

/** A course module with sensible defaults — pass `lessons`/`title` to build multi-lesson courses
 *  for reader navigation tests. `competency` defaults to null (no-research path); `makeCourse`
 *  builds its module inline with a non-null competency for the arc/competency reader tests. */
export function makeModule(overrides: Partial<Module> = {}): Module {
  return {
    id: "m-test",
    title: "Module",
    kcs: [],
    competency: null,
    objectives: [],
    lessons: [makeLesson()],
    assessment: { items: [] },
    difficultyIndex: 0.5,
    ...overrides,
  };
}

/** A library card summary for My-courses tests; mirrors the camelCase CourseSummaryView wire. */
export function makeCourseSummary(overrides: Partial<CourseSummary> = {}): CourseSummary {
  return {
    id: "course-lib",
    topic: "How HTTPS works",
    lessonTotal: 6,
    lessonsDone: 4,
    percent: 67,
    conceptTotal: 15,
    level: "intermediate",
    learnerStatus: "in_progress",
    courseStatus: "published",
    builtAt: "2026-07-01T00:00:00Z",
    lastOpenedAt: "2026-07-06T00:00:00Z",
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
    goalType: "knowledge",
    scopeNote: "",
    status: "review",
    provenance: [{ id: "src-1", title: "CLRS", url: "https://example.org/clrs", snippet: "…" }],
    modules: [
      {
        id: "m-binary_search",
        title: "Binary Search",
        kcs: ["binary_search"],
        competency: "Locate an element in a sorted collection efficiently.",
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
              passCriterion: "States O(log n) and explains the halving of the search space.",
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

/** The phase-1 brief endpoint response (POST /api/briefs): an inferred brief + the confirm
 *  clarifier, each CHOICE pre-picking the inference. For Personalize-flow tests. */
export function makeBriefResponse(overrides: Partial<BriefResponse> = {}): BriefResponse {
  return {
    brief: {
      subject: "English language proficiency",
      goal: "reach CLB 10",
      goalType: "credential",
      targetLevel: "intermediate",
      targetStandard: null,
      gap: { entryLevel: "intermediate", targetLevel: "intermediate", magnitude: "moderate" },
      assumedPrior: "everyday English",
      deliverableShape: { lessons: null },
      needsResearch: false,
      preferences: { detailDepth: "balanced", languageStyle: "balanced" },
    },
    clarifier: {
      questions: [
        {
          // Mirrors the server's build_clarifier order (R0): the goal-type question comes first.
          id: QUESTION_IDS.GOAL,
          prompt: "What kind of outcome are you after?",
          kind: "choice",
          placeholder: "",
          options: [
            { value: "knowledge", label: "Understand a topic", recommended: false },
            { value: "skill", label: "Build a skill", recommended: false },
            { value: "credential", label: "Pass a credential", recommended: true },
            { value: "behavior", label: "Change a behavior", recommended: false },
          ],
        },
        {
          id: QUESTION_IDS.LEVEL,
          prompt: "What's your current level with this?",
          kind: "choice",
          placeholder: "",
          options: [
            { value: "novice", label: "Beginner", recommended: false },
            { value: "intermediate", label: "Intermediate", recommended: true },
            { value: "advanced", label: "Advanced", recommended: false },
          ],
        },
        {
          id: QUESTION_IDS.KNOWLEDGE,
          prompt: "What are you already comfortable with?",
          kind: "text",
          placeholder: "everyday English",
          options: [],
        },
        {
          id: QUESTION_IDS.BACKGROUND,
          prompt: "What's your background, and why this goal?",
          kind: "text",
          placeholder: "what you do",
          options: [],
        },
        {
          id: QUESTION_IDS.DETAIL,
          prompt: "How much depth do you want?",
          kind: "choice",
          placeholder: "",
          options: [{ value: "balanced", label: "Balanced", recommended: true }],
        },
        {
          id: QUESTION_IDS.LANGUAGE,
          prompt: "What writing style fits you best?",
          kind: "choice",
          placeholder: "",
          options: [{ value: "balanced", label: "Balanced", recommended: true }],
        },
      ],
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
    gapCount: null,
    videosTotal: null,
    videosDegraded: null,
    status: null,
    ...extra,
  };
}

/** A fetch-style Response whose body streams the given SSE text frames. Pass `open: true` to leave
 *  the stream un-closed (it stays "streaming" — for asserting the live transcript mid-build). */
export function sseStreamResponse(
  frames: string[],
  init: { ok?: boolean; status?: number; open?: boolean; headers?: Record<string, string> } = {},
) {
  const { ok = true, status = 200, open = false, headers = {} } = init;
  return {
    ok,
    status,
    headers: new Headers(headers),
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
    source: null,
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

/** URL-routed fetch stub for App-level integration tests. StudioApp fetches GET /api/runs
 *  (sidebar) + GET /api/settings (capability probes) on mount AND streams builds, so the mock
 *  routes by URL: history/settings/briefs/me are JSON, the build is an SSE stream, course-by-id
 *  serves opens. Unhandled URLs throw — surfaced as a rejected fetch, which the app's hooks
 *  treat as fail-closed (e.g. no `me` handler → not admin). */
export function routedFetch(
  handlers: {
    runs?: unknown;
    events?: unknown;
    build?: unknown;
    course?: unknown;
    settings?: unknown;
    brief?: unknown;
    me?: unknown;
    progress?: unknown;
    library?: unknown;
    activity?: unknown;
    bookmarks?: unknown;
  } = {},
) {
  return vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (/\/api\/runs\/[^/]+\/cancel$/.test(url) && method === "POST") {
      return Promise.resolve({ ok: true, status: 202 });
    }
    if (url.includes("/api/briefs")) {
      return Promise.resolve({ ok: true, json: async () => handlers.brief });
    }
    // A reattached running run polls its live event log — distinct from the run-history list.
    if (/\/api\/runs\/[^/]+\/events$/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => handlers.events ?? [] });
    }
    if (url.includes("/api/runs")) {
      return Promise.resolve({ ok: true, json: async () => handlers.runs ?? [] });
    }
    if (url.includes("/api/me") && handlers.me !== undefined) {
      return Promise.resolve({ ok: true, json: async () => handlers.me });
    }
    if (url.includes("/api/settings")) {
      const settings = handlers.settings ?? {
        secrets: [],
        pipeline: "stub",
        supportsLessonRegeneration: true,
      };
      return Promise.resolve({ ok: true, json: async () => settings });
    }
    if (/\/api\/courses\/[^/]+\/progress$/.test(url)) {
      const progress = handlers.progress ?? { courseId: "", objectives: [], lessons: [] };
      return Promise.resolve({ ok: true, json: async () => progress });
    }
    // Progress writes (objective / lesson / opened) succeed silently — the app treats them as
    // best-effort, and an unhandled URL here would loop the reader's reconcile-on-failure path.
    if (
      /\/api\/courses\/[^/]+\/progress\/(objective|lesson|opened)$/.test(url) &&
      method === "PUT"
    ) {
      return Promise.resolve({ ok: true, status: 204 });
    }
    // The reader's study-minutes heartbeat succeeds silently — fire-and-forget telemetry.
    if (url.includes("/api/activity/heartbeat") && method === "PUT") {
      return Promise.resolve({ ok: true, status: 204 });
    }
    // Bookmarks: GET serves the list; the toggle's writes succeed silently (the hook is
    // optimistic and only refetches on failure).
    if (url.includes("/api/bookmarks")) {
      if (method === "GET") {
        return Promise.resolve({ ok: true, json: async () => handlers.bookmarks ?? [] });
      }
      return Promise.resolve({ ok: true, status: 204 });
    }
    // The activity snapshot (streaks / heat / feed) — carries a ?tz= query.
    if (/\/api\/activity(\?|$)/.test(url) && method === "GET") {
      const activity = handlers.activity ?? {
        stats: { currentStreak: 0, longestStreak: 0, minutesThisWeek: 0, conceptsThisWeek: 0 },
        heat: [],
        week: [],
        feed: [],
      };
      return Promise.resolve({ ok: true, json: async () => activity });
    }
    if (url.includes("/api/courses/stream")) {
      return Promise.resolve(handlers.build);
    }
    // The bare collection GET (the My-courses library) — ≠ POST /api/courses (a build) and
    // ≠ course-by-id (which has a path segment after /courses).
    if (/\/api\/courses$/.test(url) && method === "GET") {
      return Promise.resolve({ ok: true, json: async () => handlers.library ?? [] });
    }
    if (/\/api\/courses\/[^/?]+$/.test(url)) {
      // course-by-id: exactly one path segment after /courses/, no query (≠ the stream URL)
      return Promise.resolve({ ok: true, json: async () => handlers.course });
    }
    throw new Error(`routedFetch: unhandled URL ${url}`);
  });
}
