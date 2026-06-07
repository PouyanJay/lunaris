/**
 * Wire types for the P7.5 infer-and-confirm clarifier (phase 1 of the build).
 *
 * `POST /api/briefs` returns a {@link BriefResponse}: the interpreter's inferred {@link CourseBrief}
 * plus a {@link Clarifier} (the confirm questions, each pre-picking the inference as `recommended`).
 * The learner's confirmed answers come back to the build as a {@link Clarification} on the stream.
 * All keys are camelCase — the API's wire contract.
 */

export type Level = "novice" | "intermediate" | "advanced" | "expert" | "n/a";
export type DetailDepth = "concise" | "balanced" | "in_depth";
export type LanguageStyle = "simple" | "balanced" | "sophisticated" | "scientific";
/** What kind of outcome the goal is (CQ Phase 1.0) — the deliverable shape branches on it. */
export type GoalType = "knowledge" | "skill" | "credential" | "behavior";
/** How large the entry → target leap is (CQ Phase 1.0) — sizes research depth. */
export type GapMagnitude = "small" | "moderate" | "large";

export interface BriefPreferences {
  detailDepth: DetailDepth;
  languageStyle: LanguageStyle;
}

export interface TargetStandard {
  name: string;
  authorityHint: string;
}

/** The entry → target distance the course must close (CQ Phase 1.0). */
export interface Gap {
  entryLevel: Level;
  targetLevel: Level;
  magnitude: GapMagnitude;
}

/** The interpreter's reading of the request — shown as a summary at the top of the panel. */
export interface CourseBrief {
  subject: string;
  goal: string;
  goalType: GoalType;
  targetLevel: Level;
  targetStandard: TargetStandard | null;
  gap: Gap;
  assumedPrior: string;
  deliverableShape: { lessons: number | null };
  needsResearch: boolean;
  preferences: BriefPreferences;
}

export type ClarifierKind = "choice" | "text";

export interface ClarifierOption {
  value: string;
  label: string;
  /** The interpreter's inferred value — pre-selected so the zero-friction path is a single confirm. */
  recommended: boolean;
}

export interface ClarifierQuestion {
  id: string;
  prompt: string;
  kind: ClarifierKind;
  /** Present for a CHOICE question. */
  options: ClarifierOption[];
  /** Hint for a TEXT question (seeded from the inference). */
  placeholder: string;
}

export interface Clarifier {
  questions: ClarifierQuestion[];
}

export interface BriefResponse {
  brief: CourseBrief;
  clarifier: Clarifier;
}

/** The learner's confirmed answers, merged onto the brief server-side before the build. */
export interface Clarification {
  goalType?: GoalType;
  targetLevel?: Level;
  assumedKnown?: string;
  background?: string;
  detailDepth?: DetailDepth;
  languageStyle?: LanguageStyle;
}

/** The clarifier question ids (the server's `build_clarifier` contract) — centralized so the
 *  answer→Clarification mapping references them in one place rather than scattering string literals. */
export const QUESTION_IDS = {
  GOAL: "goal",
  LEVEL: "level",
  KNOWLEDGE: "knowledge",
  BACKGROUND: "background",
  DETAIL: "detail",
  LANGUAGE: "language",
} as const;
