import { useEffect, useRef, useState } from "react";

import type { RegenerateMode } from "../../lib/videoJobs";
import { Button } from "../primitives/Button";
import styles from "./RegenerateMenu.module.css";

const MODE_META: Record<RegenerateMode, { label: string; description: string }> = {
  retry: { label: "Retry", description: "Re-render the same storyboard." },
  simpler: { label: "Simpler", description: "Plan fewer, plainer scenes." },
  fresh: { label: "Fresh take", description: "Plan it again from scratch." },
  add_narration: { label: "Add narration", description: "Add a voiceover to this video." },
};

interface RegenerateMenuProps {
  /** Which modes apply to this video's state — e.g. a failed video can't reuse a contract. */
  available: RegenerateMode[];
  onSelect: (mode: RegenerateMode) => void;
  busy?: boolean;
  /** Trigger label — "Regenerate" (a ready video) or "Try again" (a failed one). */
  triggerLabel?: string;
}

/** The regenerate menu (explainer-video V6-T2): a trigger that opens a WAI-ARIA menu of the
 *  applicable re-run modes. Each mode re-enters the pipeline at its own node server-side. Keyboard:
 *  Enter/Space opens onto the first item, arrows move, Escape closes (focus returns to the trigger),
 *  a click outside dismisses. */
export function RegenerateMenu({
  available,
  onSelect,
  busy = false,
  triggerLabel = "Regenerate",
}: RegenerateMenuProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemsRef = useRef<(HTMLButtonElement | null)[]>([]);

  // Focus the first item when the menu opens (the WAI-ARIA menu-button entry behaviour).
  useEffect(() => {
    if (open) itemsRef.current[0]?.focus();
  }, [open]);

  // Dismiss on a click outside the trigger + menu.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }

  function choose(mode: RegenerateMode) {
    close(true);
    onSelect(mode);
  }

  function focusAt(index: number) {
    itemsRef.current[index]?.focus();
  }

  function onItemKeyDown(event: React.KeyboardEvent, index: number) {
    const last = available.length - 1;
    switch (event.key) {
      case "ArrowDown":
        focusAt(index === last ? 0 : index + 1);
        break;
      case "ArrowUp":
        focusAt(index === 0 ? last : index - 1);
        break;
      case "Home":
        focusAt(0);
        break;
      case "End":
        focusAt(last);
        break;
      case "Escape":
        close(true);
        break;
      default:
        return; // not a key we handle — leave default behaviour
    }
    event.preventDefault();
  }

  if (available.length === 0) return null;

  return (
    <div className={styles.wrap}>
      <Button
        ref={triggerRef}
        variant="secondary"
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        {busy ? "Regenerating…" : triggerLabel}
      </Button>
      {open && (
        <div ref={menuRef} className={styles.menu} role="menu" aria-label="Regenerate video">
          {available.map((mode, index) => (
            <button
              key={mode}
              ref={(node) => {
                itemsRef.current[index] = node;
              }}
              type="button"
              role="menuitem"
              className={styles.item}
              onClick={() => choose(mode)}
              onKeyDown={(event) => onItemKeyDown(event, index)}
            >
              <span className={styles.itemLabel}>{MODE_META[mode].label}</span>
              <span className={styles.itemDescription}>{MODE_META[mode].description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
