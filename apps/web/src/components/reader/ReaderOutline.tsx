import { useRef } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import type { LessonState } from "../../lib/lessonState";
import { LessonChip } from "../course/LessonChip";
import styles from "./ReaderOutline.module.css";

/** One lesson entry in the outline; `index` is its position in the flattened course-wide lesson
 *  order (the value the reader focuses on), `lessonId` keys its progress state. */
export interface OutlineItem {
  index: number;
  lessonId: string;
  label: string;
}

/** A module and its lessons in the outline. */
export interface OutlineGroup {
  moduleId: string;
  moduleTitle: string;
  items: OutlineItem[];
}

const STATE_TEXT: Record<Exclude<LessonState, "up_next">, string> = {
  done: "Done",
  in_progress: "In progress",
};

/** One section of the focused lesson, nested under its outline entry (Field Guide): the arc's
 *  bookends and phases with their live read state from the reader's scroll-spy. */
export interface LessonSectionEntry {
  id: string;
  label: string;
  state: "done" | "current" | "upcoming";
}

interface ReaderOutlineProps {
  groups: OutlineGroup[];
  activeIndex: number;
  onSelect: (index: number) => void;
  /** A lesson's progress state for its chip; absent (offline) every chip is the plain number. */
  stateFor?: ((lessonId: string) => LessonState) | undefined;
  /** The focused lesson's sections, nested under its entry; absent hides the section level. */
  sections?: LessonSectionEntry[] | undefined;
  /** Jump the reading pane to a section (its `data-section` id). */
  onSelectSection?: ((id: string) => void) | undefined;
  /** Extra classes for the outline root — the reader uses this to turn it into a drawer on phones. */
  className?: string | undefined;
}

/** The course outline (TOC): lessons grouped under their module titles, each with the shared
 *  numbered progress chip (✓ done / amber in-progress). The active lesson is marked `aria-current`
 *  and reads as a raised, hairline-framed chip; each entry is a button so the outline is fully
 *  keyboard-operable.
 *  Progress state is also written into the entry's text (visually hidden) — never color alone. */
export function ReaderOutline({
  groups,
  activeIndex,
  onSelect,
  stateFor,
  sections,
  onSelectSection,
  className,
}: ReaderOutlineProps) {
  const outlineRef = useRef<HTMLElement>(null);
  useAutoHideScroll(outlineRef);
  return (
    <nav
      ref={outlineRef}
      id="reader-outline"
      className={`${styles.outline} scroller ${className ?? ""}`.trim()}
      aria-label="Course outline"
    >
      {groups.map((group) => (
        <div key={group.moduleId} className={styles.group}>
          <p className={`eyebrow ${styles.groupTitle}`}>{group.moduleTitle}</p>
          <ul className={styles.items}>
            {group.items.map((item) => {
              const active = item.index === activeIndex;
              const state = stateFor ? stateFor(item.lessonId) : "up_next";
              return (
                <li key={item.index}>
                  <button
                    type="button"
                    className={`${styles.item} ${active ? styles.active : ""}`}
                    aria-current={active ? "page" : undefined}
                    onClick={() => onSelect(item.index)}
                  >
                    <LessonChip number={item.index + 1} state={state} size="sm" />
                    <span className={styles.itemLabel}>{item.label}</span>
                    {state !== "up_next" && <span className="sr-only">{STATE_TEXT[state]}</span>}
                  </button>
                  {/* The focused lesson unfolds its sections (Field Guide): where the learner is
                      in the arc, what's read past (✓), and one-click jumps to each region. */}
                  {active && onSelectSection && sections && sections.length > 0 && (
                    <ul className={styles.sections} aria-label="Lesson sections">
                      {sections.map((section) => (
                        <li key={section.id}>
                          <button
                            type="button"
                            className={`${styles.section} ${
                              section.state === "current" ? styles.sectionCurrent : ""
                            }`.trim()}
                            data-state={section.state}
                            aria-current={section.state === "current" ? "location" : undefined}
                            onClick={() => onSelectSection(section.id)}
                          >
                            <span className={styles.sectionMark} aria-hidden="true">
                              {section.state === "done" ? "✓" : ""}
                            </span>
                            <span className={styles.itemLabel}>{section.label}</span>
                            {section.state === "done" && <span className="sr-only">Read</span>}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
