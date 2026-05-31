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

export interface Module {
  id: string;
  title: string;
  kcs: string[];
  objectives: Objective[];
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
export type RunStatus = "running" | "completed" | "failed";

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
 * `reasoning` → `text`; `tool_call` → `tool` + `toolArgs`; `tool_result` → `tool` + `result`;
 * `todo` → `todos`.
 */
export interface AgentEvent {
  kind: AgentEventKind;
  runId: string;
  sequence: number;
  text: string | null;
  tool: string | null;
  toolArgs: Record<string, unknown> | null;
  result: string | null;
  todos: AgentTodo[] | null;
}
