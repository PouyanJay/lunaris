import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import styles from "./Select.module.css";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

interface SelectProps<T extends string> {
  /** The selected value (controlled). */
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  id?: string;
  disabled?: boolean;
  /** Points at the visible label element (the row's `<label>` / eyebrow). */
  "aria-labelledby"?: string;
  /** `full` stretches to its row (model / preset); `compact` sizes to content (the length rows). */
  size?: "full" | "compact";
}

/** A single-choice dropdown (the WAI-ARIA listbox pattern) that always opens BELOW its trigger, in a
 *  hairline-bordered, shadowed popover — unlike a native `<select>`, whose menu the browser places
 *  over the control. A button shows the current label; opening reveals a `role="listbox"` of
 *  options. Keyboard: ↑/↓ move, Home/End jump, Enter/Space select, Esc closes (focus returns to the
 *  trigger); the open list holds focus and tracks the active option via `aria-activedescendant`.
 *  Clicking outside closes it. Use in place of `<select>` where the native menu's placement/《styling
 *  can't be controlled. */
export function Select<T extends string>({
  value,
  options,
  onChange,
  id,
  disabled = false,
  "aria-labelledby": labelledBy,
  size = "full",
}: SelectProps<T>) {
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (index: number) => `${baseId}-opt-${index}`;
  const [open, setOpen] = useState(false);
  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const [activeIndex, setActiveIndex] = useState(selectedIndex);

  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selected = options[selectedIndex];

  // Focus the list on open (so arrow keys drive it) and start from the current value.
  useEffect(() => {
    if (open) {
      setActiveIndex(selectedIndex);
      listRef.current?.focus();
    }
  }, [open, selectedIndex]);

  // Close on an outside pointer press — the listbox popover is not a modal.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [open]);

  function choose(index: number) {
    const option = options[index];
    if (option) onChange(option.value);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onButtonKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  }

  function onListKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((i) => Math.min(options.length - 1, i + 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((i) => Math.max(0, i - 1));
        break;
      case "Home":
        event.preventDefault();
        setActiveIndex(0);
        break;
      case "End":
        event.preventDefault();
        setActiveIndex(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(activeIndex);
        break;
      case "Escape":
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  }

  return (
    <div ref={rootRef} className={styles.root} data-size={size}>
      <button
        ref={buttonRef}
        id={id}
        type="button"
        className={styles.trigger}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={labelledBy ? `${labelledBy} ${baseId}-value` : undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onButtonKeyDown}
      >
        <span id={`${baseId}-value`} className={styles.value}>
          {selected?.label ?? value}
        </span>
        <span className={styles.chevron} aria-hidden="true" />
      </button>
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          className={styles.list}
          aria-labelledby={labelledBy}
          aria-activedescendant={optionId(activeIndex)}
          onKeyDown={onListKeyDown}
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              id={optionId(index)}
              role="option"
              aria-selected={option.value === value}
              className={styles.option}
              data-active={index === activeIndex || undefined}
              // Pointer, not click, so the selection lands before the outside-press handler runs.
              onPointerDown={(event) => {
                event.preventDefault();
                choose(index);
              }}
              onPointerEnter={() => setActiveIndex(index)}
            >
              <span className={styles.check} aria-hidden="true">
                {option.value === value && (
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M3.5 8.5l3 3 6-7"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </span>
              <span className={styles.optionLabel}>{option.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
