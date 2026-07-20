import type {
  AssessmentItem,
  Lesson,
  MerrillSegments,
  Resource,
  Visual,
} from "../../types/course";

/** One screen of the guided Learn mode (Focus Flow). */
export interface LessonStep {
  /** Stable within a lesson: `${sectionId}:${ordinal}`. */
  id: string;
  /** Mirrors the Read mode's section ids (expects / phase keys / selfCheck / assessment). */
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

function wordCount(text: string): number {
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
    const blockWords = wordCount(block);
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

/** Cut the lesson into Learn-mode steps, deterministically, from the data the pipeline already
 *  ships: the expects bookend as an intro, each phase's prose in ~120-word chunks, its visuals
 *  and curated resources as their own steps, self-check items as closing check steps, and the
 *  module assessment as the finale. An empty lesson yields no steps (the caller falls back). */
export function buildLessonSteps({ lesson, phases, assessment }: LessonStepsInput): LessonStep[] {
  const steps: LessonStep[] = [];
  const expects = lesson.expects ?? [];
  if (expects.length > 0) {
    steps.push({
      id: "expects:0",
      sectionId: "expects",
      sectionLabel: "What this lesson expects",
      kind: "intro",
      items: expects,
      words: wordCount(expects.join(" ")),
    });
  }
  for (const { key, label, cue } of phases) {
    const segment = lesson.segments[key];
    let ordinal = 0;
    for (const chunk of packChunks(splitBlocks(segment.prose))) {
      steps.push({
        id: `${key}:${ordinal++}`,
        sectionId: key,
        sectionLabel: label,
        cue,
        kind: "content",
        markdown: chunk,
        words: wordCount(chunk),
      });
    }
    for (const visual of segment.visuals) {
      steps.push({
        id: `${key}:${ordinal++}`,
        sectionId: key,
        sectionLabel: label,
        cue,
        kind: "visual",
        visual,
        words: 0,
      });
    }
    if ((segment.resources ?? []).length > 0) {
      steps.push({
        id: `${key}:${ordinal++}`,
        sectionId: key,
        sectionLabel: label,
        cue,
        kind: "resources",
        resources: segment.resources,
        words: 0,
      });
    }
  }
  (lesson.selfCheck ?? []).forEach((item, index) => {
    steps.push({
      id: `selfCheck:${index}`,
      sectionId: "selfCheck",
      sectionLabel: "Self-check",
      kind: "check",
      items: [item],
      words: wordCount(item),
    });
  });
  if (assessment.length > 0) {
    steps.push({
      id: "assessment:0",
      sectionId: "assessment",
      sectionLabel: "Check your understanding",
      kind: "assessment",
      assessment,
      words: 0,
    });
  }
  return steps;
}
