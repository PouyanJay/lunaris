import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

/** Sidebar width bounds (px). The rail stays usable at the floor and never eats the canvas at the
 *  ceiling. Exported so the resize control can advertise them via aria-valuemin/max and the tests
 *  assert against one source of truth. */
export const SIDEBAR_MIN_WIDTH = 220;
export const SIDEBAR_MAX_WIDTH = 420;
export const SIDEBAR_DEFAULT_WIDTH = 264;
/** Width (px) of the collapsed mini rail — wide enough for a centred 28px icon button with breathing
 *  room. The rail shows icon-only actions; the run history and resize splitter are hidden there. */
export const SIDEBAR_RAIL_WIDTH = 56;
/** Keyboard resize step (px) per arrow-key press on the splitter. */
const SIDEBAR_KEYBOARD_STEP = 16;
/** Where the collapse + width preference is persisted (per-device, so localStorage not the URL). */
const STORAGE_KEY = "lunaris.sidebar";

export interface SidebarLayout {
  /** Whether the rail is collapsed to zero width (canvas full-bleed). */
  collapsed: boolean;
  /** Current expanded width in px (preserved while collapsed, restored on expand). */
  width: number;
  /** True only while a pointer drag is in progress — lets the shell suppress its width transition
   *  so the rail tracks the cursor 1:1 instead of easing behind it. */
  resizing: boolean;
  toggleCollapsed: () => void;
  /** Begin a pointer-drag resize from the splitter. */
  startResize: (event: PointerEvent) => void;
  /** Resize via the keyboard when the splitter is focused (Arrow keys, Home/End). */
  nudgeWidth: (event: KeyboardEvent) => void;
}

interface PersistedLayout {
  collapsed: boolean;
  width: number;
}

const clampWidth = (width: number): number =>
  Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));

/** Read the persisted preference, tolerating absent/corrupt storage (falls back to the defaults). */
function readPersisted(): PersistedLayout {
  const fallback: PersistedLayout = { collapsed: false, width: SIDEBAR_DEFAULT_WIDTH };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<PersistedLayout>;
    return {
      collapsed: typeof parsed.collapsed === "boolean" ? parsed.collapsed : false,
      width: typeof parsed.width === "number" ? clampWidth(parsed.width) : SIDEBAR_DEFAULT_WIDTH,
    };
  } catch {
    return fallback;
  }
}

/**
 * Owns the sidebar's collapse state and resizable width, persisted per-device. The width survives a
 * collapse (so expanding restores it) and is clamped to a sane range. Resizing is driven either by a
 * pointer drag on the splitter (1:1, transition suppressed) or the keyboard when it's focused.
 */
export function useSidebarLayout(): SidebarLayout {
  const initial = readPersisted();
  const [collapsed, setCollapsed] = useState(initial.collapsed);
  const [width, setWidth] = useState(initial.width);
  const [resizing, setResizing] = useState(false);
  // Mirror width for the pointer-move closure, which captures the start width once at press time.
  const widthRef = useRef(width);
  widthRef.current = width;

  // Persist on every change — cheap, and keeps the preference durable without an explicit save.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ collapsed, width }));
    } catch {
      // A storage failure (private mode / quota) must not break the layout — degrade silently.
    }
  }, [collapsed, width]);

  const toggleCollapsed = useCallback(() => setCollapsed((prev) => !prev), []);

  const startResize = useCallback((event: PointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = widthRef.current;
    setResizing(true);

    const onMove = (move: globalThis.PointerEvent) => {
      setWidth(clampWidth(startWidth + (move.clientX - startX)));
    };
    const onUp = () => {
      setResizing(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    // Window-level listeners so the drag keeps tracking even over the canvas (e.g. the graph), which
    // would otherwise swallow the pointer events.
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  const nudgeWidth = useCallback((event: KeyboardEvent) => {
    const step = {
      ArrowLeft: -SIDEBAR_KEYBOARD_STEP,
      ArrowRight: SIDEBAR_KEYBOARD_STEP,
    }[event.key];
    if (step !== undefined) {
      event.preventDefault();
      setWidth((prev) => clampWidth(prev + step));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setWidth(SIDEBAR_MIN_WIDTH);
    } else if (event.key === "End") {
      event.preventDefault();
      setWidth(SIDEBAR_MAX_WIDTH);
    }
  }, []);

  return { collapsed, width, resizing, toggleCollapsed, startResize, nudgeWidth };
}
