import { useEffect, type RefObject } from "react";

/** Marks a scroll container as actively scrolling so its scrollbar can fade in while in use and back
 *  out once idle. While the element scrolls, `data-scroll-active="true"` is set; it is cleared
 *  `idleMs` after the last scroll. Pair with the global `.scroller` styles, which reveal the thin
 *  thumb when the element is active, hovered, or focus-within and hide it otherwise.
 *
 *  Pure presentation: scroll position and behaviour are untouched, and the gutter is reserved in CSS
 *  so revealing the thumb never shifts the content. */
export function useAutoHideScroll(ref: RefObject<HTMLElement | null>, idleMs = 800): void {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let timer: number | undefined;

    const onScroll = () => {
      element.dataset.scrollActive = "true";
      if (timer !== undefined) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        delete element.dataset.scrollActive;
      }, idleMs);
    };

    element.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      element.removeEventListener("scroll", onScroll);
      if (timer !== undefined) window.clearTimeout(timer);
      delete element.dataset.scrollActive;
    };
  }, [ref, idleMs]);
}
