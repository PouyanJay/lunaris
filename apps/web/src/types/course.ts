/**
 * TypeScript mirror of the Lunaris course-object schema (packages/runtime schema,
 * serialised camelCase). Only the slices the prerequisite-graph explorer consumes are
 * modelled; extend as more of the course surface is built out.
 */

import type { CoverJobStatus, CoverStylePreset } from "../lib/coverJobs";
import type { VideoJobStatus } from "../lib/videoJobs";
import type { GoalType } from "./clarifier";

export type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

/** How a KC is learned (CQ Phase 1.0) — drives Phase 2's resource + media shape. */
export type Modality = "receptive" | "productive" | "procedural" | "conceptual";

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
  /** How this KC is learned (CQ Phase 1.0); absent on pre-Phase-1 courses. */
  modality?: Modality | null;
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

/** A worked example: a literal/naive phrasing shown beside its improved rewrite, with a note on why
 *  the rewrite is better. Reuses `TransformSide` for parity with before-after; worked examples are
 *  prose, so a side's `language` is typically null. Shown side by side (the contrast is the point) —
 *  distinct from `before-after`, which the reader toggles between. */
export interface WorkedExampleSpec {
  type: "worked-example";
  title: string | null;
  literal: TransformSide;
  improved: TransformSide;
  note: string | null;
}

export type VisualSpec =
  | FlowSpec
  | TreeSpec
  | StepsSpec
  | ComparisonSpec
  | TimelineSpec
  | BeforeAfterSpec
  | WorkedExampleSpec;

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
  /** The build-time explainer video stitched onto the lesson (V4), if the course shipped one. The
   *  hero resolves it and flags it outdated once the lesson is revised (V6-T3). */
  video?: VideoArtifact | null;
}

/** One assessment item (mirrors Item). `answer` is the model answer, often absent. */
export interface AssessmentItem {
  id: string;
  prompt: string;
  /** The objective/KC id this item assesses. */
  objective: string;
  answer: string | null;
  /** Backward design (CQ Phase 4.1): the concrete, gradeable bar a passing response must clear.
   *  Empty on pre-P4 courses (the reader shows no check line). */
  passCriterion: string;
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

/** A key-gated capability that degrades to a keyless local fallback (mirrors CapabilityName). */
export type CapabilityName = "llm" | "embeddings" | "search" | "video" | "cover";

/** Whether a capability ran on its keyed provider or its keyless fallback (mirrors CapabilityMode). */
export type CapabilityMode = "live" | "fallback";

/** Which provider produced one capability's contribution to a course (mirrors CapabilityBuildTag,
 *  keyless-fallbacks T5). Captured at finalize and persisted: the honest, permanent record of the
 *  fallback that built a Draft course — distinct from the live capability badge, which reflects the
 *  current key state. `provider` is the human label of the provider in effect. */
export interface CapabilityBuildTag {
  capability: CapabilityName;
  mode: CapabilityMode;
  provider: string;
}

/** The scope-realism band (CQ Phase 3.1): an honest effort/timeline + what this course does and
 *  does not get you, computed at finalize from the brief. `null` on a pre-Phase-3 course → no band. */
export interface CourseScope {
  /** Human-readable effort/timeline band, e.g. "~6–10 weeks · self-paced". "" = unknown. */
  effort: string;
  /** What the course DOES get you — concrete outcomes, one line each. */
  delivers: string[];
  /** What it does NOT get you — honest exclusions, one line each. */
  excludes: string[];
}

/** Which explainer video a job produces (mirrors the runtime `VideoKind`). */
export type VideoKind = "summary" | "overview" | "lesson";

/** A generated video as it rides in the course payload (explainer-video V2/V5): its grounding
 *  provenance + playback metadata. The reader resolves the short-lived signed playback URL from
 *  `provenance.jobId` via `GET /api/videos/{jobId}`. `provenance` is absent on a FAILED video. */
export interface VideoArtifact {
  kind: VideoKind;
  status: VideoJobStatus;
  /** The source job — present even when FAILED (unlike `provenance`), so the regenerate menu (V6)
   *  can re-run any artifact, finished or not. */
  jobId?: string | null;
  provenance?: VideoProvenance | null;
  narrated: boolean;
  durationS?: number | null;
}

/** A scene the build shipped best-effort because a gate couldn't fully clear it (the 'publish
 *  anyway' degrade): a spatial defect Gate B couldn't repair, a sync imperfection, or a figure the
 *  factual gate couldn't verify. `issues` are the human-readable reasons, surfaced in the reader's
 *  degraded badge so the artifact is honest about what is imperfect. */
export interface DegradedScene {
  sceneId: string;
  issues: string[];
}

/** Where a generated video came from — structural provenance (CLAUDE.md). `jobId` is also the
 *  handle the reader uses to fetch the video's signed URLs. `lessonId` is null for course-level. */
export interface VideoProvenance {
  jobId: string;
  courseId: string;
  lessonId?: string | null;
  kind: VideoKind;
  model: string;
  contractHash: string;
  inputHash: string;
  claimIds: string[];
  generatedAt: string;
  /** Scenes shipped flagged because a gate couldn't fully clear them; empty/absent when every scene
   *  passed cleanly (older artifacts omit it). */
  degradedScenes?: DegradedScene[];
}

/** The course's opening videos — the V5 Overview section: a SUMMARY trailer and an OVERVIEW intro.
 *  Each is absent until the build stitches it (or its render degraded); the whole block is absent on
 *  a pre-V5 / video-off course → the reader shows no Overview section. */
export interface CourseVideos {
  summary?: VideoArtifact | null;
  overview?: VideoArtifact | null;
}

/** Where a generated course cover came from — structural provenance (CLAUDE.md; mirrors the runtime
 *  `CoverProvenance`). The anti-slop record: which image model drew it (`source`/`model`) and which
 *  Claude models wrote the house-style prompt (`artDirectorModel`) and inspected the result
 *  (`qaModel`), plus the exact `prompt` and how many render→QA rounds it took (`qaAttempts`). */
export interface CoverProvenance {
  jobId: string;
  courseId: string;
  source: string;
  model: string;
  artDirectorModel: string;
  qaModel: string;
  stylePreset: CoverStylePreset;
  prompt: string;
  qaAttempts: number;
  inputHash: string;
  generatedAt: string;
}

/** A course's AI cover image as it rides in the course payload (mirrors the runtime `CoverArtifact`).
 *  Keeps a `jobId` HANDLE only — the reader resolves a fresh signed URL on demand via
 *  `GET /api/covers/{jobId}`, never a stale persisted URL. `provenance` is absent on a FAILED cover;
 *  `jobId` is present even when FAILED so a regenerate can re-run it. Absent on a course that never
 *  got an AI cover (keyless account) → the reader shows the Typographic cover instead. */
export interface CoverArtifact {
  status: CoverJobStatus;
  jobId?: string | null;
  provenance?: CoverProvenance | null;
}

export interface Course {
  id: string;
  topic: string;
  goalConcept: string;
  /** The course-level goal classification carried from the brief (CQ Phase 1.0). */
  goalType: GoalType;
  /** An honest caveat when a research-needing goal couldn't be grounded (CQ Phase 1.6); "" when
   *  fully grounded or not research-needing. The reader shows it so a generic course is never
   *  presented as an authoritative guide to the standard. */
  scopeNote: string;
  /** The scope-realism band (CQ Phase 3.1); null/absent on pre-Phase-3 courses → reader shows no band. */
  scope?: CourseScope | null;
  graph: PrerequisiteGraph;
  modules: Module[];
  provenance: Citation[];
  /** Which provider produced each key-gated capability (keyless-fallbacks T5); captured at finalize
   *  and persisted, so a Draft course carries the honest record of the fallback that built it.
   *  Absent on pre-T5 courses → the reader shows no build-provenance strip. */
  buildCapabilities?: CapabilityBuildTag[];
  /** The course's opening videos (explainer-video V5); absent on a pre-V5 / video-off course. */
  videos?: CourseVideos | null;
  /** The course's AI cover image (course-cover-images); absent until a cover job settles READY, or
   *  on a keyless account that never enqueues one → the reader shows the Typographic cover. */
  cover?: CoverArtifact | null;
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
  | "coverage_verified"
  | "lesson_videos"
  | "run_completed";

/** One module's KC mapping on CURRICULUM_DESIGNED (mirrors CurriculumModuleMap) — pairs with
 *  MODULE_AUTHORED events so the P8 blueprint can light each mapped node as its module lands. */
export interface CurriculumModuleMap {
  id: string;
  title: string;
  kcs: string[];
}

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
  /** Promised competencies left unbuilt on COVERAGE_VERIFIED (CQ Phase 4.2); 0 == clean. */
  gapCount: number | null;
  /** Lesson-video tally on LESSON_VIDEOS (explainer-video V4): total enqueued, and how many
   *  degraded (failed). `videosDegraded` > 0 renders the Videos phase amber. Null elsewhere. */
  videosTotal: number | null;
  videosDegraded: number | null;
  status: CourseStatus | null;
  /** P8 control room: the validated structure + goal on GRAPH_BUILT, and the module → KC
   *  mapping on CURRICULUM_DESIGNED. Absent/null on other stages AND in pre-P8 run logs —
   *  the blueprint renders only when they exist (strapline honesty). */
  graph?: PrerequisiteGraph | null;
  goalConcept?: string | null;
  modules?: CurriculumModuleMap[] | null;
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

/** The library's level pill, bucketed server-side from the graph's mean KC difficulty. */
export type CourseLevel = "beginner" | "intermediate" | "advanced";

/** Where THIS user stands on a course — distinct from the operational RunStatus and the
 *  pedagogical CourseStatus. */
export type LearnerCourseStatus = "not_started" | "in_progress" | "completed";

/** One My-courses library card (mirrors CourseSummaryView, serialised camelCase). `id` is the
 *  course id the card opens; `topic` names the course, same word as `Course`/`CourseRun`.
 *  `level` is null for a graphless course; `builtAt` is the run's finish time. */
export interface CourseSummary {
  id: string;
  topic: string;
  lessonTotal: number;
  lessonsDone: number;
  percent: number;
  conceptTotal: number;
  level: CourseLevel | null;
  learnerStatus: LearnerCourseStatus;
  courseStatus: CourseStatus;
  builtAt: string;
  lastOpenedAt: string | null;
  /** The AI cover handle (course-cover-images) — kept for the reader's regenerate + lightbox, and
   *  the card's fallback path for a cover still generating. Absent on a keyless / pre-covers /
   *  cover-less course. */
  cover?: CoverArtifact | null;
  /** The READY cover's display-size thumb, PRE-SIGNED in the `/api/courses` payload
   *  (library-instant-covers): the grid renders it straight, with no per-card signed-URL fetch.
   *  `thumbUrlLight` is its dual-theme twin (null for a dark-only cover). Both absent/null when
   *  there's nothing to sign — the card then uses the `cover` handle or the Typographic fallback. */
  thumbUrl?: string | null;
  thumbUrlLight?: string | null;
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
