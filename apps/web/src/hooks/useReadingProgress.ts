import { useEffect, useState, type RefObject } from "react";

/** Track how far a scrollable pane has been read, as a rounded 0–100 percent.
 *
 *  Scroll position is the Field Guide's read signal: the percent is `scrollTop` over the
 *  scrollable range, measured on scroll (rAF-throttled) and window resize. `resetKey` names the
 *  content identity (the focused lesson id) — changing it re-measures from the top. The state
 *  only updates when the rounded value moves, so a full read costs at most 100 re-renders.
 *
 *  Edge geometry: an unlaid-out pane (jsdom, first paint) reads 0; content that fits entirely in
 *  the viewport reads 100 — everything is on screen. */
export function useReadingProgress(
  paneRef: RefObject<HTMLElement | null>,
  resetKey: unknown,
): number {
  const [percent, setPercent] = useState(0);

  useEffect(() => {
    const pane = paneRef.current;
    if (!pane) return;
    let frame = 0;
    const measure = () => {
      const { scrollTop, scrollHeight, clientHeight } = pane;
      let next = 0;
      if (scrollHeight > 0) {
        const range = scrollHeight - clientHeight;
        next = range <= 0 ? 100 : Math.min(100, Math.round((scrollTop / range) * 100));
      }
      setPercent(next);
    };
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        measure();
      });
    };
    measure();
    pane.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      pane.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [paneRef, resetKey]);

  return percent;
}
