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
