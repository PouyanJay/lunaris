import { useState, type RefObject } from "react";

import { usePaneObserver } from "./usePaneObserver";

/** Track how far a scrollable pane has been read, as a rounded 0–100 percent.
 *
 *  Scroll position is the Field Guide's read signal: the percent is `scrollTop` over the
 *  scrollable range; `resetKey` names the content identity (the focused lesson id) so a lesson
 *  change re-measures from the top. The state only updates when the rounded value moves, so a
 *  full read costs at most 100 re-renders.
 *
 *  Edge geometry: an unlaid-out pane (jsdom, first paint) reads 0; content that fits entirely in
 *  the viewport reads 100 — everything is on screen. */
export function useReadingProgress(
  paneRef: RefObject<HTMLElement | null>,
  resetKey: unknown,
): number {
  const [percent, setPercent] = useState(0);

  usePaneObserver(paneRef, resetKey, ({ scrollTop, scrollHeight, clientHeight }) => {
    let next = 0;
    if (scrollHeight > 0) {
      const range = scrollHeight - clientHeight;
      next = range <= 0 ? 100 : Math.min(100, Math.round((scrollTop / range) * 100));
    }
    setPercent(next);
  });

  return percent;
}
