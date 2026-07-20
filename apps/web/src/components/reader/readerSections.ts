import type { LessonSectionEntry } from "./ReaderOutline";

interface SectionEntriesInput {
  /** The arc bookends — an empty list means the lesson has no such section. */
  expects: string[];
  selfCheck: string[];
  /** Items in the module assessment shown on this lesson (0 off the module's last lesson). */
  assessmentCount: number;
  /** The teaching phases in reading order (the reader's PHASES). */
  phases: ReadonlyArray<{ key: string; label: string }>;
  activeSection: string | null;
  passedSections: ReadonlySet<string>;
}

function sectionStateFor(
  id: string,
  activeSection: string | null,
  passedSections: ReadonlySet<string>,
): LessonSectionEntry["state"] {
  if (id === activeSection) return "current";
  return passedSections.has(id) ? "done" : "upcoming";
}

/** The focused lesson's sections in reading order — the outline's nested level. Ids mirror the
 *  reading pane's `data-section` anchors; state comes from the scroll-spy (current wins over
 *  done, so the section under the reading line never shows a tick). */
export function buildSectionEntries(input: SectionEntriesInput): LessonSectionEntry[] {
  const { expects, selfCheck, assessmentCount, phases, activeSection, passedSections } = input;
  return [
    ...(expects.length > 0 ? [{ id: "expects", label: "What this lesson expects" }] : []),
    ...phases.map(({ key, label }) => ({ id: key, label })),
    ...(selfCheck.length > 0 ? [{ id: "selfCheck", label: "Self-check" }] : []),
    ...(assessmentCount > 0 ? [{ id: "assessment", label: "Check your understanding" }] : []),
  ].map((entry) => ({
    ...entry,
    state: sectionStateFor(entry.id, activeSection, passedSections),
  }));
}
