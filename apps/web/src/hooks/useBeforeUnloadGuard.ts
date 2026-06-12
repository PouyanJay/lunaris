import { useEffect } from "react";

/** While `active`, intercept tab close/navigation with the browser's native "leave site?"
 *  confirm. Used by device-compute builds, where closing the tab kills the build — the guard is
 *  the last line of the tab-open contract (the dropdown hint and in-build notice state it; this
 *  catches the reflex Cmd-W anyway). Browsers ignore custom text, so none is set. */
export function useBeforeUnloadGuard(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const confirmLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // The legacy compat leg: some engines (older Chromium, Safari) key the confirm dialog off
      // returnValue rather than preventDefault. Both are required to cover the field.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", confirmLeave);
    return () => window.removeEventListener("beforeunload", confirmLeave);
  }, [active]);
}
