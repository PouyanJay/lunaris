import { useState, type RefObject } from "react";

import { usePaneObserver } from "./usePaneObserver";

/** What the spy knows about the pane's `[data-section]` regions. */
export interface SectionSpyState {
  /** The section the reader is currently in — the last one whose top has crossed the pane's
   *  reading line (40% down the viewport); the first section before any scrolling. */
  activeSection: string | null;
  /** Sections whose bottom has scrolled fully above the pane — "read past". */
  passedSections: ReadonlySet<string>;
}

const EMPTY: SectionSpyState = { activeSection: null, passedSections: new Set() };

function sameState(a: SectionSpyState, b: SectionSpyState): boolean {
  if (a.activeSection !== b.activeSection) return false;
  if (a.passedSections.size !== b.passedSections.size) return false;
  for (const id of a.passedSections) if (!b.passedSections.has(id)) return false;
  return true;
}

/** Measure the spy state off the pane's live geometry. An unlaid-out pane (jsdom, first paint)
 *  reports the first section active and nothing passed. */
function measureSections(pane: HTMLElement): SectionSpyState {
  const els = Array.from(pane.querySelectorAll<HTMLElement>("[data-section]"));
  const first = els[0]?.dataset["section"] ?? null;
  const paneRect = pane.getBoundingClientRect();
  if (els.length === 0 || paneRect.height <= 0) {
    return { activeSection: first, passedSections: new Set() };
  }
  const readingLine = paneRect.top + paneRect.height * 0.4;
  let active: string | null = null;
  const passed = new Set<string>();
  for (const el of els) {
    const id = el.dataset["section"];
    if (!id) continue;
    const rect = el.getBoundingClientRect();
    if (rect.bottom <= paneRect.top + 1) passed.add(id);
    if (rect.top <= readingLine) active = id;
  }
  return { activeSection: active ?? first, passedSections: passed };
}

/** Scroll-spy over the reading pane's `[data-section]` regions, re-measured when `resetKey` (the
 *  focused lesson id) changes. State only updates when the derived values move, so scrolling
 *  within a section costs nothing. */
export function useSectionSpy(
  paneRef: RefObject<HTMLElement | null>,
  resetKey: unknown,
): SectionSpyState {
  const [state, setState] = useState<SectionSpyState>(EMPTY);

  usePaneObserver(paneRef, resetKey, (pane) => {
    const next = measureSections(pane);
    setState((prev) => (sameState(prev, next) ? prev : next));
  });

  return state;
}
