/**
 * TypeScript mirror of the Lunaris course-object schema (packages/runtime schema,
 * serialised camelCase). Only the slices the prerequisite-graph explorer consumes are
 * modelled; extend as more of the course surface is built out.
 */

export type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

export type CourseStatus =
  | "diagnosing"
  | "mapping"
  | "sequencing"
  | "authoring"
  | "verifying"
  | "review"
  | "published";

/** The atomic teachable unit (KC). */
export interface KnowledgeComponent {
  id: string;
  label: string;
  definition: string;
  /** Normalised 0..1 difficulty. */
  difficulty: number;
  bloomCeiling: BloomLevel;
  /** Citation ids grounding this KC. */
  sources: string[];
}

/** A directed prerequisite: `from` must be learned before `to`. */
export interface PrerequisiteEdge {
  from: string;
  to: string;
  /** Judge confidence 0..1. */
  strength: number;
}

export interface PrerequisiteGraph {
  nodes: KnowledgeComponent[];
  edges: PrerequisiteEdge[];
  /** The learner's known boundary (KC ids already mastered). */
  frontier: string[];
  isAcyclic: boolean;
  /** Difficulty-tiebroken topological order of KC ids. */
  topoOrder: string[];
}

export interface Objective {
  statement: string;
  bloomLevel: BloomLevel;
  kc: string;
  assessedBy: string[];
}

/** The verifier's verdict on a claim's grounding (mirrors VerifierStatus). */
export type VerifierStatus = "unverified" | "supported" | "revise" | "cut";

/** How a diagram is expressed on the wire (mirrors VisualKind). */
export type VisualKind = "mermaid" | "svg" | "chart" | "spec";

/** Mayer multimedia-design checks attached to a visual (mirrors MayerFlags). */
export interface MayerFlags {
  coherence: boolean;
  signaling: boolean;
  spatialContiguity: boolean;
  redundancy: boolean;
}

/** A typed, bounded visual specification the branded renderer draws with its own components
 *  (mirrors the Pydantic VisualSpec union, discriminated by `type`). */
export interface FlowNode {
  id: string;
  label: string;
}
export interface FlowEdge {
  from: string;
  to: string;
  label: string | null;
}
export interface FlowSpec {
  type: "flow";
  title: string | null;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface TreeNode {
  id: string;
  label: string;
  parentId: string | null;
}
export interface TreeSpec {
  type: "tree";
  title: string | null;
  nodes: TreeNode[];
}

export interface StepItem {
  title: string;
  detail: string | null;
}
export interface StepsSpec {
  type: "steps";
  title: string | null;
  steps: StepItem[];
}

export interface ComparisonRow {
  label: string;
  values: string[];
}
export interface ComparisonSpec {
  type: "comparison";
  title: string | null;
  columns: string[];
  rows: ComparisonRow[];
}

export interface TimelineEvent {
  label: string;
  detail: string | null;
  when: string | null;
}
export interface TimelineSpec {
  type: "timeline";
  title: string | null;
  events: TimelineEvent[];
}

export type VisualSpec = FlowSpec | TreeSpec | StepsSpec | ComparisonSpec | TimelineSpec;

/** A diagram attached to a segment. `source` is diagram-as-code (Mermaid) — the renderer's
 *  fallback; `spec` is the typed branded-renderer specification when the agent emitted one. */
export interface Visual {
  kind: VisualKind;
  source: string;
  rendered: string | null;
  spec: VisualSpec | null;
  mayerChecks: MayerFlags;
}

/** A single factual assertion in a segment, grounded (or cut) by the verifier. `supportedBy` is a
 *  Citation id resolved against `Course.provenance`. */
export interface Claim {
  text: string;
  supportedBy: string | null;
  verifierStatus: VerifierStatus;
}

/** The content of one Merrill phase: prose plus its diagrams and grounded claims. */
export interface Segment {
  prose: string;
  visuals: Visual[];
  claims: Claim[];
}

/** Merrill's First Principles — the four instructional phases of a lesson. */
export interface MerrillSegments {
  activate: Segment;
  demonstrate: Segment;
  apply: Segment;
  integrate: Segment;
}

/** Gagné's nine events of instruction, tracked per lesson (mirrors GagneFlags). */
export interface GagneFlags {
  gainAttention: boolean;
  stateObjective: boolean;
  recallPrior: boolean;
  presentContent: boolean;
  guideLearning: boolean;
  elicitPerformance: boolean;
  provideFeedback: boolean;
  assessPerformance: boolean;
  enhanceTransfer: boolean;
}

export interface Lesson {
  id: string;
  segments: MerrillSegments;
  gagne: GagneFlags;
  /** Estimated intrinsic cognitive load for the lesson. */
  loadEstimate: number;
}

/** One assessment item (mirrors Item). `answer` is the model answer, often absent. */
export interface AssessmentItem {
  id: string;
  prompt: string;
  /** The objective/KC id this item assesses. */
  objective: string;
  answer: string | null;
}

export interface Assessment {
  items: AssessmentItem[];
}

export interface Module {
  id: string;
  title: string;
  kcs: string[];
  objectives: Objective[];
  lessons: Lesson[];
  assessment: Assessment;
  difficultyIndex: number;
}

export interface Citation {
  id: string;
  title: string | null;
  url: string | null;
  snippet: string | null;
}

export interface Course {
  id: string;
  topic: string;
  goalConcept: string;
  graph: PrerequisiteGraph;
  modules: Module[];
  provenance: Citation[];
  status: CourseStatus;
}

/** A pipeline stage boundary, streamed live while a course builds (mirrors ProgressStage). */
export type ProgressStage =
  | "run_started"
  | "concepts_extracted"
  | "graph_built"
  | "curriculum_designed"
  | "module_authored"
  | "claims_verified"
  | "run_completed";

/** One streamed build update (mirrors the ProgressEvent schema, serialised camelCase). */
export interface ProgressEvent {
  stage: ProgressStage;
  label: string;
  runId: string;
  sequence: number;
  kcCount: number | null;
  edgeCount: number | null;
  moduleCount: number | null;
  moduleId: string | null;
  claimsTotal: number | null;
  claimsSupported: number | null;
  claimsCut: number | null;
  status: CourseStatus | null;
}

/** The operational lifecycle of a build run for the sidebar history (mirrors RunStatus). */
export type RunStatus = "running" | "completed" | "failed" | "cancelled";

/**
 * One row in the run-history index — a single course build listed in the sidebar (mirrors the
 * CourseRun schema, serialised camelCase). `id` is the course_id the run re-opens with; `runId`
 * is the correlation id; timestamps are owned by the run, not the course.
 */
export interface CourseRun {
  id: string;
  runId: string;
  topic: string;
  status: RunStatus;
  kcCount: number;
  moduleCount: number;
  createdAt: string;
  updatedAt: string;
}

/** The kind of a fine-grained agent-transcript beat (mirrors AgentEventKind). */
export type AgentEventKind = "reasoning" | "tool_call" | "tool_result" | "todo";

/** One todo/plan item the agent is tracking. */
export interface AgentTodo {
  content: string;
  status: string;
}

/**
 * One fine-grained event from the deep agent's execution, streamed live to the transcript
 * (mirrors the AgentEvent schema, serialised camelCase). Fields are populated per `kind`:
 * `reasoning` → `text` (a whole beat) or `delta` (one streaming token chunk to append to the live
 * beat); `tool_call` → `tool` + `toolArgs`; `tool_result` → `tool` + `result`; `todo` → `todos`.
 */
export interface AgentEvent {
  kind: AgentEventKind;
  runId: string;
  sequence: number;
  /** The coarse pipeline stage active when this event fired (null for the "intro" beats before the
   *  first stage), so the live timeline buckets it under its phase deterministically. */
  stage: ProgressStage | null;
  text: string | null;
  delta: string | null;
  tool: string | null;
  toolArgs: Record<string, unknown> | null;
  result: string | null;
  todos: AgentTodo[] | null;
}

/**
 * One persisted row of a run's build log (mirrors the RunEvent schema, serialised camelCase). The
 * two live SSE channels are persisted into one ordered log so a past build can be replayed; `kind`
 * says which wire shape the `payload` carries. Rows arrive ordered by `seq` (the run-scoped emission
 * index) from `GET /api/runs/{runId}/events`.
 */
export interface RunEvent {
  runId: string;
  courseId: string;
  seq: number;
  kind: "progress" | "agent";
  payload: ProgressEvent | AgentEvent;
}
