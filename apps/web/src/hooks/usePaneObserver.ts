import { useEffect, useRef, type RefObject } from "react";

/** Observe a scrollable pane: run `measure` once on mount, then on every scroll (rAF-throttled)
 *  and window resize, re-running from scratch when `resetKey` (the pane's content identity)
 *  changes. Owns the listener + frame lifecycle so consumers only write their measurement.
 *  `measure` rides a ref — consumers may pass a fresh closure every render without re-binding. */
export function usePaneObserver(
  paneRef: RefObject<HTMLElement | null>,
  resetKey: unknown,
  measure: (pane: HTMLElement) => void,
): void {
  const measureRef = useRef(measure);
  measureRef.current = measure;

  useEffect(() => {
    const pane = paneRef.current;
    if (!pane) return;
    let frame = 0;
    const run = () => measureRef.current(pane);
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        run();
      });
    };
    run();
    pane.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      pane.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [paneRef, resetKey]);
}
