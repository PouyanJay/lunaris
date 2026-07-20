/** Scroll an element into view (centred by default — pass "start" for section jumps), honouring
 *  reduced-motion — and a no-op where the platform doesn't implement it (jsdom under tests).
 *  Keeps the cross-highlight code free of guards. */
export function scrollIntoViewSafe(
  element: Element | null | undefined,
  reduceMotion: boolean,
  block: ScrollLogicalPosition = "center",
): void {
  if (!element || typeof element.scrollIntoView !== "function") return;
  element.scrollIntoView({ block, behavior: reduceMotion ? "auto" : "smooth" });
}
