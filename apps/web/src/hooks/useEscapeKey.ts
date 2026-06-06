import { useEffect } from "react";

/** Run `onEscape` when Escape is pressed while `active` — the keyboard-dismiss contract for
 *  overlays/drawers (WCAG 2.2). Listener is attached only while active and cleaned up on close. */
export function useEscapeKey(active: boolean, onEscape: () => void): void {
  useEffect(() => {
    if (!active) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onEscape();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, onEscape]);
}
