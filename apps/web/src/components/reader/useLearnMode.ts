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

/** The stored mode preference; guided Learn is the default (Focus Flow), and a storage-less
 *  environment (SSR, blocked storage) falls back to it. `watch` (Cinema) is only ever *effective*
 *  where a ready chaptered video exists — the reader clamps it to Learn otherwise — but it persists
 *  here so the preference survives lessons that happen to have no video. */
function storedReaderMode(): ReaderMode {
  try {
    const stored = localStorage.getItem(READER_MODE_KEY);
    if (stored === "read") return "read";
    if (stored === "watch") return "watch";
    return "learn";
  } catch {
    return "learn";
  }
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
  mode: ReaderMode;
  /** Convenience for gating the long-form regions. */
  reading: boolean;
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

/** Focus Flow's state: the Learn/Read preference (persisted per device), the step position in
 *  the focused lesson (per-visit, reset on lesson change), and the step-derived structures the
 *  reader composes — steps, sections, and section read-state. */
export function useLearnMode({
  lesson,
  lessonId,
  phases,
  assessment,
}: UseLearnModeInput): UseLearnModeResult {
  const [mode, setMode] = useState<ReaderMode>(storedReaderMode);
  const selectMode = useCallback((next: ReaderMode) => {
    setMode(next);
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
    mode,
    reading: mode === "read",
    selectMode,
    stepIndex,
    setStepIndex,
    steps,
    sections,
    sectionProgress,
    firstStepOf,
  };
}
