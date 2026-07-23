import type {
  AssessmentItem,
  Lesson,
  MerrillSegments,
  Resource,
  Segment,
  Visual,
} from "../../types/course";

/** One screen of the guided Learn mode (Focus Flow). */
export interface LessonStep {
  /** Stable within a lesson: `${sectionId}:${ordinal}`. */
  id: string;
  /** The outline's section ids (expects / phase keys / selfCheck / assessment). */
  sectionId: string;
  sectionLabel: string;
  /** The phase's arc cue, for the card eyebrow (content/visual/resources steps). */
  cue?: string;
  kind: "intro" | "content" | "visual" | "resources" | "check" | "assessment";
  markdown?: string;
  /** Intro bullets (expects) or the single self-check item. */
  items?: string[];
  visual?: Visual;
  resources?: Resource[];
  assessment?: AssessmentItem[];
  /** Reading words this step costs — the time-left metric sums the remainder. */
  words: number;
}

/** One idea per screen: a step targets this many words before the next block overflows it. */
const TARGET_WORDS = 120;

function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

/** Split prose into top-level markdown blocks: blank lines separate blocks, EXCEPT inside a
 *  code fence or a `:::` directive container — those stay atomic whatever they contain. */
function splitBlocks(prose: string): string[] {
  const blocks: string[] = [];
  let current: string[] = [];
  let inFence = false;
  let directiveDepth = 0;
  for (const line of prose.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
      inFence = !inFence;
    } else if (!inFence && trimmed.startsWith(":::")) {
      // A bare run of colons closes the container; a named one (`:::deeper[…]`) opens it.
      if (/^:+$/.test(trimmed)) directiveDepth = Math.max(0, directiveDepth - 1);
      else directiveDepth += 1;
    }
    if (trimmed === "" && !inFence && directiveDepth === 0) {
      if (current.length > 0) {
        blocks.push(current.join("\n"));
        current = [];
      }
      continue;
    }
    current.push(line);
  }
  if (current.length > 0) blocks.push(current.join("\n"));
  return blocks;
}

/** Greedily pack blocks into ~TARGET_WORDS chunks. Blocks are never split; a single oversized
 *  block stands alone; a heading always opens a new chunk (and stays with what follows it). */
function packChunks(blocks: string[]): string[] {
  const chunks: string[] = [];
  let current: string[] = [];
  let currentWords = 0;
  const flush = () => {
    if (current.length > 0) {
      chunks.push(current.join("\n\n"));
      current = [];
      currentWords = 0;
    }
  };
  for (const block of blocks) {
    const blockWords = countWords(block);
    const isHeading = block.trimStart().startsWith("#");
    if (isHeading || (currentWords > 0 && currentWords + blockWords > TARGET_WORDS)) flush();
    current.push(block);
    currentWords += blockWords;
  }
  flush();
  return chunks;
}

interface LessonStepsInput {
  lesson: Lesson;
  /** The teaching phases in reading order (the reader's PHASES). */
  phases: ReadonlyArray<{ key: keyof MerrillSegments; label: string; cue: string }>;
  /** The module assessment shown on this lesson ([] off the module's last lesson). */
  assessment: AssessmentItem[];
}

type Phase = LessonStepsInput["phases"][number];

function buildIntroStep(expects: string[]): LessonStep[] {
  if (expects.length === 0) return [];
  return [
    {
      id: "expects:0",
      sectionId: "expects",
      sectionLabel: "What this lesson expects",
      kind: "intro",
      items: expects,
      words: countWords(expects.join(" ")),
    },
  ];
}

function buildPhaseSteps({ key, label, cue }: Phase, segment: Segment): LessonStep[] {
  const steps: LessonStep[] = [];
  const base = { sectionId: key, sectionLabel: label, cue };
  let ordinal = 0;
  for (const chunk of packChunks(splitBlocks(segment.prose))) {
    steps.push({
      ...base,
      id: `${key}:${ordinal++}`,
      kind: "content",
      markdown: chunk,
      words: countWords(chunk),
    });
  }
  for (const visual of segment.visuals) {
    steps.push({ ...base, id: `${key}:${ordinal++}`, kind: "visual", visual, words: 0 });
  }
  if ((segment.resources ?? []).length > 0) {
    steps.push({
      ...base,
      id: `${key}:${ordinal++}`,
      kind: "resources",
      resources: segment.resources,
      words: 0,
    });
  }
  return steps;
}

function buildSelfCheckSteps(selfCheck: string[]): LessonStep[] {
  return selfCheck.map((item, index) => ({
    id: `selfCheck:${index}`,
    sectionId: "selfCheck",
    sectionLabel: "Self-check",
    kind: "check" as const,
    items: [item],
    words: countWords(item),
  }));
}

function buildAssessmentStep(assessment: AssessmentItem[]): LessonStep[] {
  if (assessment.length === 0) return [];
  return [
    {
      id: "assessment:0",
      sectionId: "assessment",
      sectionLabel: "Check your understanding",
      kind: "assessment",
      assessment,
      words: 0,
    },
  ];
}

/** Cut the lesson into Learn-mode steps, deterministically, from the data the pipeline already
 *  ships: the expects bookend as an intro, each phase's prose in ~120-word chunks, its visuals
 *  and curated resources as their own steps, self-check items as closing check steps, and the
 *  module assessment as the finale. An empty lesson yields no steps (the caller falls back). */
export function buildLessonSteps({ lesson, phases, assessment }: LessonStepsInput): LessonStep[] {
  return [
    ...buildIntroStep(lesson.expects ?? []),
    ...phases.flatMap((phase) => buildPhaseSteps(phase, lesson.segments[phase.key])),
    ...buildSelfCheckSteps(lesson.selfCheck ?? []),
    ...buildAssessmentStep(assessment),
  ];
}

/** Collapse whitespace + lowercase so a matched sentence lines up with its chunk despite the
 *  block-join newlines and any casing drift. */
function normalizeProse(text: string): string {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

/** The step a "locate in the lesson" click on a claim should land on (claim-lesson-backlink). When
 *  the claim confidently matched a prose sentence (`matchedSentence`), the content step whose
 *  ~120-word chunk contains that sentence; otherwise the phase's first step, so a click is never a
 *  dead end. `undefined` when the phase has no steps. Indices are into the full `steps` list. */
export function stepIndexForClaim(
  steps: LessonStep[],
  phaseKey: string,
  matchedSentence: string | null,
): number | undefined {
  const needle = matchedSentence ? normalizeProse(matchedSentence) : null;
  let firstOfPhase: number | undefined;
  let sentenceHit: number | undefined;
  steps.forEach((step, index) => {
    if (step.sectionId !== phaseKey) return;
    if (firstOfPhase === undefined) firstOfPhase = index;
    if (
      sentenceHit === undefined &&
      needle &&
      step.kind === "content" &&
      normalizeProse(step.markdown ?? "").includes(needle)
    ) {
      sentenceHit = index;
    }
  });
  return sentenceHit ?? firstOfPhase;
}

/** A section of the step sequence (steps are contiguous per section by construction). */
export interface StepSection {
  id: string;
  label: string;
  firstIndex: number;
}

/** The sections a step sequence walks through, in order, with their first step index. */
export function buildSections(steps: LessonStep[]): StepSection[] {
  const sections: StepSection[] = [];
  steps.forEach((step, index) => {
    if (sections[sections.length - 1]?.id !== step.sectionId) {
      sections.push({ id: step.sectionId, label: step.sectionLabel, firstIndex: index });
    }
  });
  return sections;
}

/** Section read-state at a step position: the section holding the position is active; a section
 *  is passed once the position has moved beyond its last step. One rule for the section map and
 *  the course outline, so the two can never disagree. */
export function sectionProgressAt(
  sections: StepSection[],
  stepIndex: number,
): { activeSection: string | null; passedSections: ReadonlySet<string> } {
  let active: string | null = null;
  const passed = new Set<string>();
  sections.forEach((section, index) => {
    if (section.firstIndex <= stepIndex) active = section.id;
    const next = sections[index + 1];
    if (next && next.firstIndex <= stepIndex) passed.add(section.id);
  });
  if (active) passed.delete(active);
  return { activeSection: active, passedSections: passed };
}
