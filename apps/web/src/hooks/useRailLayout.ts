import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

/** Reader rail width bounds (px). The rail stays readable at the floor and never crowds the reading
 *  column at the ceiling. Exported so the splitter advertises them via aria-valuemin/max and the
 *  tests assert against one source of truth. */
export const RAIL_MIN_WIDTH = 248;
export const RAIL_MAX_WIDTH = 520;
export const RAIL_DEFAULT_WIDTH = 320;
/** Keyboard resize step (px) per arrow-key press on the splitter. */
const RAIL_KEYBOARD_STEP = 16;
/** Default localStorage key — the reader rail. Pass a distinct key for another rail surface (e.g.
 *  the config rail) so the two persist independently and don't share collapse/width state. */
const DEFAULT_STORAGE_KEY = "lunaris.reader.rail";

export interface RailLayout {
  /** Whether the rail is collapsed (the reading column goes full-bleed on wide screens). */
  collapsed: boolean;
  /** Current expanded width in px (preserved while collapsed, restored on expand). */
  width: number;
  /** True only while a pointer drag is in progress — lets the reader suppress its width transition
   *  so the rail tracks the cursor 1:1 instead of easing behind it. */
  resizing: boolean;
  toggleCollapsed: () => void;
  /** Begin a pointer-drag resize from the splitter (the rail sits on the right, so dragging left
   *  widens it). */
  startResize: (event: PointerEvent) => void;
  /** Resize via the keyboard when the splitter is focused (Arrow keys, Home/End). */
  nudgeWidth: (event: KeyboardEvent) => void;
}

interface PersistedLayout {
  collapsed: boolean;
  width: number;
}

const clampWidth = (width: number): number =>
  Math.min(RAIL_MAX_WIDTH, Math.max(RAIL_MIN_WIDTH, width));

/** Read the persisted preference, tolerating absent/corrupt storage (falls back to the defaults). */
function readPersisted(storageKey: string): PersistedLayout {
  const fallback: PersistedLayout = { collapsed: false, width: RAIL_DEFAULT_WIDTH };
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<PersistedLayout>;
    return {
      collapsed: typeof parsed.collapsed === "boolean" ? parsed.collapsed : false,
      width: typeof parsed.width === "number" ? clampWidth(parsed.width) : RAIL_DEFAULT_WIDTH,
    };
  } catch {
    return fallback;
  }
}

/**
 * Owns the annotation rail's collapse state and resizable width on wide screens, persisted per
 * device. The width survives a collapse (so expanding restores it) and is clamped to a sane range.
 * Resizing is driven either by a pointer drag on the splitter (1:1, transition suppressed) or the
 * keyboard when it's focused. (Narrow screens render the rail as a drawer and ignore this.)
 *
 * `storageKey` selects where the preference persists, so distinct rail surfaces (the reader rail vs
 * the config rail) keep independent collapse/width state.
 */
export function useRailLayout(storageKey: string = DEFAULT_STORAGE_KEY): RailLayout {
  const initial = readPersisted(storageKey);
  const [collapsed, setCollapsed] = useState(initial.collapsed);
  const [width, setWidth] = useState(initial.width);
  const [resizing, setResizing] = useState(false);
  // Mirror width for the pointer-move closure, which captures the start width once at press time.
  const widthRef = useRef(width);
  widthRef.current = width;

  // Persist on every change — cheap, and keeps the preference durable without an explicit save.
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ collapsed, width }));
    } catch {
      // A storage failure (private mode / quota) must not break the layout — degrade silently.
    }
  }, [storageKey, collapsed, width]);

  const toggleCollapsed = useCallback(() => setCollapsed((prev) => !prev), []);

  const startResize = useCallback((event: PointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthRef.current;
    setResizing(true);

    const onMove = (move: globalThis.PointerEvent) => {
      // Rail is on the right edge → dragging the splitter LEFT (negative delta) widens it.
      setWidth(clampWidth(startWidth - (move.clientX - startX)));
    };
    const onUp = () => {
      setResizing(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    // Window-level listeners so the drag keeps tracking even over the reading pane.
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  const nudgeWidth = useCallback((event: KeyboardEvent) => {
    // Left arrow widens (rail grows leftward); right arrow narrows — mirrors the drag direction.
    const step = {
      ArrowLeft: RAIL_KEYBOARD_STEP,
      ArrowRight: -RAIL_KEYBOARD_STEP,
    }[event.key];
    if (step !== undefined) {
      event.preventDefault();
      setWidth((prev) => clampWidth(prev + step));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setWidth(RAIL_MIN_WIDTH);
    } else if (event.key === "End") {
      event.preventDefault();
      setWidth(RAIL_MAX_WIDTH);
    }
  }, []);

  return { collapsed, width, resizing, toggleCollapsed, startResize, nudgeWidth };
}
