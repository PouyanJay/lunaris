import { useCallback, useEffect, useMemo, useState } from "react";

import type { AssessmentItem, Lesson, MerrillSegments } from "../../types/course";
import { buildLessonSteps, buildSections, sectionProgressAt, type LessonStep } from "./lessonSteps";

/** Where the Learn/Watch mode preference persists (per-device, house `lunaris.reader.*` keys). */
export const READER_MODE_KEY = "lunaris.reader.mode";

export type ReaderMode = "learn" | "watch";

/** The persisted mode preference, or `null` when the learner has made no explicit choice on this
 *  device. The reader reads `null` as "apply the front-door default" — Watch when the lesson has a
 *  ready chaptered video, else Learn (Focus Flow). `watch` persists even on lessons without a video
 *  so the preference survives (Watch then shows the generate affordance). A storage-less environment
 *  (SSR, blocked storage) reads as `null`; a legacy `read` value (Read mode is retired) also reads as
 *  `null`, so those learners land on the front-door default. */
function storedPreference(): ReaderMode | null {
  try {
    const stored = localStorage.getItem(READER_MODE_KEY);
    return stored === "watch" || stored === "learn" ? stored : null;
  } catch {
    return null;
  }
}

/** The mode actually shown, resolved from the learner's `preference`, whether Watch is offered at all
 *  (`watchOffered` — an online reader that can reach the video service), and whether the focused
 *  lesson has a ready chaptered video (`watchAvailable`, the front-door trigger). Offline (Watch not
 *  offered) always resolves to Learn. Otherwise an explicit Learn/Watch choice always wins; no explicit
 *  choice opens in Watch when a ready chaptered video exists, else Learn. An explicit Watch choice
 *  sticks even on a video-less lesson, where the Watch surface shows the generate affordance. */
export function deriveEffectiveMode(
  preference: ReaderMode | null,
  watchAvailable: boolean,
  watchOffered: boolean,
): ReaderMode {
  if (!watchOffered) return "learn";
  if (preference === "watch") return "watch";
  if (preference === "learn") return "learn";
  return watchAvailable ? "watch" : "learn";
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
  /** Section read-state at the current step — the outline's Learn-mode source. */
  sectionProgress: { activeSection: string | null; passedSections: ReadonlySet<string> };
  /** A section's first step, for outline jumps; undefined for an unknown section. */
  firstStepOf: (sectionId: string) => number | undefined;
}

/** Focus Flow's state: the Learn/Watch preference (persisted per device, `null` until chosen), the
 *  step position in the focused lesson (per-visit, reset on lesson change), and the step-derived
 *  structures the reader composes — the steps and the current section read-state. */
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
    sectionProgress,
    firstStepOf,
  };
}
