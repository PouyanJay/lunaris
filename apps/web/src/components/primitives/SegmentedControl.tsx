import { useRef, type KeyboardEvent } from "react";

import styles from "./SegmentedControl.module.css";

export interface Segment<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  /** The choices, in display order. */
  segments: Segment<T>[];
  /** The selected value (controlled). */
  value: T;
  onChange: (value: T) => void;
  /** Accessible name for the group (a visible label should also point here via `aria-labelledby`). */
  label?: string;
  "aria-labelledby"?: string;
}

/** A compact, accessible segmented control (WAI-ARIA radiogroup): joined buttons where exactly one
 *  is selected. Arrow keys + Home/End move the selection (roving tabindex); the active segment is
 *  the only tab stop. For small enumerations (search depth, target level) where a dropdown is
 *  heavier than the choice deserves. */
export function SegmentedControl<T extends string>({
  segments,
  value,
  onChange,
  label,
  "aria-labelledby": labelledBy,
}: SegmentedControlProps<T>) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = segments.findIndex((s) => s.value === value);
    if (index < 0) return;
    let next = -1;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % segments.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (index - 1 + segments.length) % segments.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = segments.length - 1;
    const target = next < 0 ? undefined : segments[next];
    if (!target) return;
    event.preventDefault();
    onChange(target.value);
    refs.current[target.value]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      aria-labelledby={labelledBy}
      className={styles.group}
    >
      {segments.map((segment) => {
        const selected = segment.value === value;
        return (
          <button
            key={segment.value}
            ref={(node) => {
              refs.current[segment.value] = node;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            className={styles.segment}
            onClick={() => onChange(segment.value)}
            onKeyDown={onKeyDown}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
