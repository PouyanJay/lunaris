import { useCallback, useEffect, useMemo, useState } from "react";

import type { AssessmentItem, Lesson, MerrillSegments } from "../../types/course";
import {
  buildLessonSteps,
  buildSections,
  sectionProgressAt,
  type LessonStep,
  type StepSection,
} from "./lessonSteps";

/** Where the Learn/Read mode preference persists (per-device, house `lunaris.reader.*` keys). */
export const READER_MODE_KEY = "lunaris.reader.mode";

export type ReaderMode = "learn" | "read" | "watch";

/** The persisted mode preference, or `null` when the learner has made no explicit choice on this
 *  device. The reader reads `null` as "apply the front-door default" — Watch when the lesson has a
 *  ready chaptered video, else Learn (Focus Flow). `watch` persists even on lessons without a video
 *  so the preference survives; the reader clamps it to Learn where Watch cannot apply. A
 *  storage-less environment (SSR, blocked storage) reads as `null`. */
function storedPreference(): ReaderMode | null {
  try {
    const stored = localStorage.getItem(READER_MODE_KEY);
    return stored === "read" || stored === "watch" || stored === "learn" ? stored : null;
  } catch {
    return null;
  }
}

/** The mode actually shown, resolved from the learner's `preference` and whether the focused lesson
 *  has a ready chaptered video (`watchAvailable`). The front-door default: no explicit choice opens
 *  in Watch when such a video exists (else Learn); an explicit Read or Learn always wins; a stored
 *  `watch` clamps to Learn where no video exists — the preference itself is left untouched, so Watch
 *  returns on the next lesson that has one. */
export function deriveEffectiveMode(
  preference: ReaderMode | null,
  watchAvailable: boolean,
): ReaderMode {
  if (preference === "read") return "read";
  const wantsWatch = preference === "watch" || preference === null;
  return wantsWatch && watchAvailable ? "watch" : "learn";
}

interface UseLearnModeInput {
  /** The focused lesson (null before the reader has one). */
  lesson: Lesson | null;
  /** Names the lesson for the step-position reset (a new lesson starts at step one). */
  lessonId: string | null;
  phases: ReadonlyArray<{ key: keyof MerrillSegments; label: string; cue: string }>;
  /** The module assessment shown on this lesson ([] off the module's last lesson). */
  assessment: AssessmentItem[];
}

interface UseLearnModeResult {
  /** The learner's explicit choice, or `null` if none yet — the reader resolves the effective mode
   *  from this plus whether a chaptered video exists (the front-door default). */
  preference: ReaderMode | null;
  /** Switch mode and persist the choice. */
  selectMode: (mode: ReaderMode) => void;
  stepIndex: number;
  setStepIndex: (index: number) => void;
  steps: LessonStep[];
  sections: StepSection[];
  /** Section read-state at the current step — the outline's Learn-mode source. */
  sectionProgress: { activeSection: string | null; passedSections: ReadonlySet<string> };
  /** A section's first step, for outline jumps; undefined for an unknown section. */
  firstStepOf: (sectionId: string) => number | undefined;
}

/** Focus Flow's state: the Learn/Read/Watch preference (persisted per device, `null` until chosen),
 *  the step position in the focused lesson (per-visit, reset on lesson change), and the
 *  step-derived structures the reader composes — steps, sections, and section read-state. */
export function useLearnMode({
  lesson,
  lessonId,
  phases,
  assessment,
}: UseLearnModeInput): UseLearnModeResult {
  const [preference, setPreference] = useState<ReaderMode | null>(storedPreference);
  const selectMode = useCallback((next: ReaderMode) => {
    setPreference(next);
    try {
      localStorage.setItem(READER_MODE_KEY, next);
    } catch {
      // Storage unavailable — the choice still applies for this session.
    }
  }, []);

  const [stepIndex, setStepIndex] = useState(0);
  useEffect(() => {
    setStepIndex(0);
  }, [lessonId]);

  const steps = useMemo(
    () => (lesson ? buildLessonSteps({ lesson, phases, assessment }) : []),
    [lesson, phases, assessment],
  );
  const sections = useMemo(() => buildSections(steps), [steps]);
  const sectionProgress = useMemo(
    () => sectionProgressAt(sections, stepIndex),
    [sections, stepIndex],
  );
  const firstStepOf = useCallback(
    (sectionId: string) => sections.find((section) => section.id === sectionId)?.firstIndex,
    [sections],
  );

  return {
    preference,
    selectMode,
    stepIndex,
    setStepIndex,
    steps,
    sections,
    sectionProgress,
    firstStepOf,
  };
}
