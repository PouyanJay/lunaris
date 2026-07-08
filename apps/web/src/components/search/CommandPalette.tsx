import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FOCUSABLE_SELECTOR } from "../../lib/focusable";
import { searchEntries } from "../../lib/searchIndex";
import type { SearchEntry } from "../../lib/searchIndex";
import type { SearchIndexState } from "../../hooks/useSearchIndex";
import styles from "./CommandPalette.module.css";

interface CommandPaletteProps {
  open: boolean;
  index: SearchIndexState;
  onClose: () => void;
  /** Land on the picked entry (the caller routes per kind), then close. */
  onPick: (entry: SearchEntry) => void;
}

const GROUP_TITLES = { courses: "Courses", lessons: "Lessons", concepts: "Concepts" } as const;

function rowId(entry: SearchEntry): string {
  return `palette-${entry.kind}-${entry.courseId}-${entry.targetId}`;
}

/** One result group of the listbox; the active row is styled AND announced (aria-selected +
 *  the input's aria-activedescendant both key off the same row id). */
function PaletteGroup({
  kind,
  items,
  active,
  onPick,
}: {
  kind: keyof typeof GROUP_TITLES;
  items: SearchEntry[];
  active: SearchEntry | undefined;
  onPick: (entry: SearchEntry) => void;
}) {
  if (items.length === 0) return null;
  return (
    <li role="presentation">
      <p className={styles.groupLabel} role="presentation">
        {GROUP_TITLES[kind]}
      </p>
      <ul className={styles.group} role="group" aria-label={GROUP_TITLES[kind]}>
        {items.map((entry) => (
          <li
            key={rowId(entry)}
            id={rowId(entry)}
            role="option"
            aria-selected={entry === active}
            className={styles.row}
            data-active={entry === active || undefined}
          >
            <button
              type="button"
              tabIndex={-1}
              className={styles.rowButton}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onPick(entry)}
            >
              <span className={styles.rowLabel}>{entry.label}</span>
              {entry.kind !== "course" && (
                <span className={`${styles.rowHint} mono`}>{entry.courseTitle}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </li>
  );
}

/** The ⌘K command palette: search courses/lessons/concepts and jump there. Focus-trapped modal
 *  (the ConfirmDialog contract), listbox keyboard pattern — ↑/↓ move, Enter opens, Esc closes,
 *  focus stays in the input while aria-activedescendant tracks the active row. */
export function CommandPalette({ open, index, onClose, onPick }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  const results = useMemo(
    () => (index.status === "ready" ? searchEntries(index.entries, query) : null),
    [index, query],
  );
  // One flat list in display order — the keyboard walks it across group boundaries.
  const flat = useMemo(
    () => (results ? [...results.courses, ...results.lessons, ...results.concepts] : []),
    [results],
  );
  const active = flat[Math.min(activeIndex, Math.max(0, flat.length - 1))];

  // A fresh open starts clean: empty query, first row active, focus in the input; the trigger
  // gets focus back on close.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    restoreRef.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => restoreRef.current?.focus();
  }, [open]);

  // New results reset the cursor — a stale index must never point past the list.
  useEffect(() => setActiveIndex(0), [query]);

  // Esc closes; Tab is trapped (capture phase, the house modal contract).
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || dialogRef.current === null) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose]);

  if (!open) return null;

  const onInputKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, Math.max(0, flat.length - 1)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && active) {
      event.preventDefault();
      onPick(active);
    }
  };

  return createPortal(
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className={styles.dialog}
      >
        <div className={styles.inputRow}>
          <svg
            className={styles.searchIcon}
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <line x1="20.5" y1="20.5" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            placeholder="Search courses, lessons, concepts…"
            aria-label="Search courses, lessons, and concepts"
            role="combobox"
            aria-expanded={flat.length > 0}
            aria-controls="palette-results"
            aria-activedescendant={active ? rowId(active) : undefined}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onInputKeyDown}
          />
          <kbd className={`${styles.escHint} mono`}>esc</kbd>
        </div>
        <div className={styles.results}>
          {index.status === "loading" || index.status === "idle" ? (
            <p className={styles.notice} aria-live="polite">
              Indexing your courses…
            </p>
          ) : index.status === "error" ? (
            <p className={styles.notice} role="alert">
              {index.message} Close and reopen to retry.
            </p>
          ) : flat.length === 0 ? (
            <p className={styles.notice}>No matches for “{query}”.</p>
          ) : (
            <ul id="palette-results" role="listbox" aria-label="Results" className={styles.list}>
              {(["courses", "lessons", "concepts"] as const).map((kind) => (
                <PaletteGroup
                  key={kind}
                  kind={kind}
                  items={results?.[kind] ?? []}
                  active={active}
                  onPick={onPick}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
