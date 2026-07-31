import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import styles from "./Menu.module.css";

export interface MenuOption<T extends string> {
  value: T;
  label: string;
  /** The one-line consequence of choosing this. Shown under the label, never as a tooltip. */
  description: string;
}

interface MenuProps<T extends string> {
  /** The setting's name, shown as the chip's key and carried into the accessible name. */
  label: string;
  value: T;
  options: MenuOption<T>[];
  onChange: (value: T) => void;
  /** An optional hairline-divided group below the options, for a row that leads somewhere else. */
  footer?: ReactNode;
}

/** A settings menu: a compact chip that opens a list of options, each explaining what it does.
 *
 *  Keyboard behaviour is the WAI-ARIA menu pattern rather than a bare popover, because these
 *  controls sit in a toolbar a keyboard user has to be able to operate: arrows move and wrap, Home
 *  and End jump, Enter chooses, Escape closes and puts focus back on the chip. Losing focus to the
 *  body on close is the failure that strands people, so the trigger always gets it back.
 *
 *  Opens downward: a menu should follow the control that opened it. */
export function Menu<T extends string>({ label, value, options, onChange, footer }: MenuProps<T>) {
  const [open, setOpen] = useState(false);
  /** Index to focus once the panel has mounted; null when the panel was opened by pointer. */
  const [focusOnOpen, setFocusOnOpen] = useState<number | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();
  const current = options.find((option) => option.value === value) ?? options[0];

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  // Pointer anywhere else dismisses. mousedown rather than click so a press outside closes before
  // the click lands on whatever is underneath.
  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (
        itemRefs.current.some((item) => item?.closest(`[data-menu="${menuId}"]`)?.contains(target))
      )
        return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, menuId]);

  // Land focus once the panel is actually in the DOM. An effect, not requestAnimationFrame: rAF
  // never flushes in the test environment, and in a browser it would race a fast keypress.
  useEffect(() => {
    if (!open || focusOnOpen === null) return;
    itemRefs.current[focusOnOpen]?.focus();
    setFocusOnOpen(null);
  }, [open, focusOnOpen]);

  /** Focus an option by index, wrapping at both ends so the list is a ring, not a dead end. */
  const focusAt = useCallback(
    (index: number) => {
      const count = options.length;
      const wrapped = ((index % count) + count) % count;
      itemRefs.current[wrapped]?.focus();
    },
    [options.length],
  );

  function openAndFocusCurrent() {
    setOpen(true);
    setFocusOnOpen(
      Math.max(
        0,
        options.findIndex((option) => option.value === value),
      ),
    );
  }

  function onTriggerKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter") {
      event.preventDefault();
      openAndFocusCurrent();
    }
  }

  function onItemKeyDown(event: React.KeyboardEvent, index: number) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusAt(index + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusAt(index - 1);
        break;
      case "Home":
        event.preventDefault();
        focusAt(0);
        break;
      case "End":
        event.preventDefault();
        focusAt(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        onChange(options[index]!.value);
        close(true);
        break;
    }
  }

  return (
    <div className={styles.wrap}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.chip}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? close(false) : setOpen(true))}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={styles.key}>{label}</span>
        <span className={styles.value}>{current?.label}</span>
        <svg
          className={styles.caret}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          className={styles.menu}
          role="menu"
          aria-label={label}
          data-menu={menuId}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            close(true);
          }}
        >
          {options.map((option, index) => (
            <button
              key={option.value}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitemradio"
              aria-checked={option.value === value}
              className={styles.item}
              onClick={() => {
                onChange(option.value);
                close(true);
              }}
              onKeyDown={(event) => onItemKeyDown(event, index)}
            >
              <svg
                className={styles.check}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M20 6L9 17l-5-5" />
              </svg>
              <span className={styles.body}>
                <span className={styles.title}>{option.label}</span>
                <span className={styles.desc}>{option.description}</span>
              </span>
            </button>
          ))}
          {footer && (
            <>
              <div className={styles.separator} />
              {footer}
            </>
          )}
        </div>
      )}
    </div>
  );
}
