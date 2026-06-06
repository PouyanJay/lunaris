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

/** One state of a before-after transformation — a labelled side the reader toggles to. `language`,
 *  when set, marks `content` as code (rendered in a code block); `caption` is an optional note. */
export interface TransformSide {
  label: string;
  content: string;
  language: string | null;
  caption: string | null;
}
/** An interactive transformation: two labelled states (e.g. naive → optimised) the reader toggles
 *  between. Distinct from `comparison` (a static N-column table). */
export interface BeforeAfterSpec {
  type: "before-after";
  title: string | null;
  before: TransformSide;
  after: TransformSide;
}

export type VisualSpec =
  | FlowSpec
  | TreeSpec
  | StepsSpec
  | ComparisonSpec
  | TimelineSpec
  | BeforeAfterSpec;

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

/** A source's authority tier (mirrors TrustTier). The user sees it; the relevance judge does not.
 *  `vouched` = a source the learner supplied directly (P6.1 manual ingest). */
export type TrustTier = "official" | "reputable" | "open" | "blocked" | "vouched";

/** How hard auto-discovery searches for a build (P6.3), chosen up front; mirrors DiscoveryDepth.
 *  `standard` is the moderate one-click default; `thorough` widens the grounding budget. */
export type DiscoveryDepth = "standard" | "thorough";

/** What KIND of source a grounding chunk is (mirrors SourceType), independent of its authority tier.
 *  snake_case values mirror the Python enum exactly (wire parity). */
export type SourceType =
  | "peer_reviewed"
  | "preprint"
  | "official"
  | "database"
  | "docs"
  | "reference"
  | "web";

/** How a trust-config entry acts on a domain (mirrors AuthorityKind, P6.2): a `spine` domain is
 *  authoritative across every topic, a `pack` domain only for runs in its `field`, a `denylist`
 *  domain is never ingested. A spine/pack hit is a tier *prior*, not a credibility boost. */
export type AuthorityKind = "spine" | "pack" | "denylist";

/** The subject field a course is classified into (mirrors SubjectField, P6.2), selecting which
 *  authority packs apply. `shared` tags top multidisciplinary venues that count across every field. */
export type SubjectField = "cs_ml" | "medicine" | "physics" | "chemistry" | "shared";

/** One row of the editable trust config (P6.2; mirrors the API SourceAuthorityView). Identity is
 *  `(domain, field)`. `field` is set only for a `pack`. */
export interface SourceAuthority {
  domain: string;
  kind: AuthorityKind;
  tier: TrustTier;
  field: SubjectField | null;
  sourceType: SourceType | null;
  note: string | null;
}

/** The kind of a curated external learning resource (mirrors ResourceKind). */
export type ResourceKind = "video" | "article" | "docs" | "practice" | "tool" | "reference";

/** A vetted external learning aid attached to a lesson phase (P7.4 — mirrors Resource, camelCase).
 *  Suggested, not part of the verified lesson. `source` is the host shown to the learner; `trustTier`
 *  + `credibility` are the user-facing quality signals; `fetchedAt` is provenance. */
export interface Resource {
  kind: ResourceKind;
  title: string;
  url: string;
  source: string;
  why: string;
  trustTier: TrustTier;
  /** 0..1 blended quality score. */
  credibility: number;
  fetchedAt: string;
  /** For video — human-readable runtime (e.g. "12:01"). */
  duration: string | null;
  author: string | null;
}

/** The content of one Merrill phase: prose plus its diagrams, grounded claims, and curated aids. */
export interface Segment {
  prose: string;
  visuals: Visual[];
  claims: Claim[];
  /** Curated external resources attached to this phase (P7.4); may be absent on pre-P7.4 courses. */
  resources: Resource[];
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
  /** The lesson arc's bookends (P7.3): the entry expectations the lesson assumes ("what this lesson
   *  expects you already know") and the self-checks the learner runs to confirm the competency.
   *  Personalized per course; may be absent on courses built before P7.3 (treat as empty). */
  expects: string[];
  selfCheck: string[];
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
  /** The researched target competency this module covers (P7.3); null on the no-research path. */
  competency: string | null;
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
  /** Source trust/provenance (P6.0). Absent on pre-P6.0 courses; null when the evidence was never
   *  classified — either way the reader shows no trust badge. `trustTier` + `credibility` are
   *  rendered; `sourceType` + `fetchedAt` are carried for parity with the wire. */
  trustTier?: TrustTier | null;
  /** 0..1 blended quality score. */
  credibility?: number | null;
  sourceType?: SourceType | null;
  fetchedAt?: string | null;
}

/** How a source entered the corpus (mirrors AcquisitionMode): a learner uploaded it, the discovery
 *  agent found it, or it was seeded from a page the build's research already fetched. */
export type AcquisitionMode = "manual" | "auto" | "seed";

/** The provenance word shown on a Corpus row, so mixed-mode corpora stay auditable at a glance. */
export const ACQUISITION_MODE_LABEL: Record<AcquisitionMode, string> = {
  manual: "Manual",
  auto: "Auto",
  seed: "Seeded",
};

/** A source-level row of a course's grounding corpus (P6.1; mirrors the API CorpusSourceView). */
export interface CorpusSource {
  sourceId: string;
  courseId: string | null;
  title: string | null;
  url: string | null;
  sourceType: SourceType | null;
  trustTier: TrustTier | null;
  credibility: number | null;
  acquisitionMode: AcquisitionMode | null;
  fetchedAt: string | null;
  chunkCount: number;
}

/** The gate's verdict for a submitted manual source (P6.1; mirrors the API IngestResultView). */
export interface IngestResult {
  accepted: boolean;
  sourceId: string;
  chunks: number;
  reason: string | null;
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
  | "brief_interpreted"
  | "standard_researched"
  | "learner_modeled"
  | "concepts_extracted"
  | "graph_built"
  | "curriculum_designed"
  | "grounding_seeded"
  | "grounding_discovered"
  | "module_authored"
  | "claims_verified"
  | "resources_curated"
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
export type AgentEventKind =
  | "reasoning"
  | "tool_call"
  | "tool_result"
  | "todo"
  | "source_evaluated";

/** One todo/plan item the agent is tracking. */
export interface AgentTodo {
  content: string;
  status: string;
}

/**
 * One discovered source the discovery sub-graph (P6.3) scored and accepted or rejected, carried on a
 * `source_evaluated` AgentEvent so the canvas can render a live source-vetting table (mirrors
 * SourceEvaluation). Trust tier + credibility are shown to the user (the intended transparency).
 */
export interface SourceEvaluation {
  kcId: string;
  domain: string;
  trustTier: TrustTier | null;
  credibility: number | null;
  sourceType: SourceType | null;
  accepted: boolean;
  reason: string;
}

/**
 * One fine-grained event from the deep agent's execution, streamed live to the transcript
 * (mirrors the AgentEvent schema, serialised camelCase). Fields are populated per `kind`:
 * `reasoning` → `text` (a whole beat) or `delta` (one streaming token chunk to append to the live
 * beat); `tool_call` → `tool` + `toolArgs`; `tool_result` → `tool` + `result`; `todo` → `todos`;
 * `source_evaluated` → `source` (one discovered source's vetting verdict).
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
  source: SourceEvaluation | null;
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
