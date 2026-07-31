import { useEffect, type RefObject } from "react";

/** Close an open overlay when the pointer goes down anywhere outside it or its trigger.
 *
 *  mousedown rather than click, so a press outside dismisses before the click lands on whatever is
 *  underneath. Shared by every overlay in the composer's dock so they cannot drift into dismissing
 *  differently from one another. */
export function useDismissable(
  open: boolean,
  onDismiss: () => void,
  triggerRef: RefObject<HTMLElement | null>,
  panelRef: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      onDismiss();
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open, onDismiss, triggerRef, panelRef]);
}
