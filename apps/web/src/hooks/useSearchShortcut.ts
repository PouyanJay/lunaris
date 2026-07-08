import { useEffect } from "react";

/**
 * The global ⌘K / Ctrl+K shortcut: opens the command palette from anywhere in the studio.
 * preventDefault stops the browser's own ⌘K (address-bar focus in some browsers) — the expected
 * behavior in this class of tool.
 */
export function useSearchShortcut(onOpen: () => void): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpen]);
}
