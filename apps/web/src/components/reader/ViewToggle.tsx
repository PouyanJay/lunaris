import { useRef, type KeyboardEvent } from "react";

import styles from "./ViewToggle.module.css";

/** The two ready-course canvas views: the lesson reader (Learn) and the prereq-graph explorer (Map). */
export type CourseView = "learn" | "map";

const OPTIONS: { value: CourseView; label: string }[] = [
  { value: "learn", label: "Learn" },
  { value: "map", label: "Map" },
];

interface ViewToggleProps {
  value: CourseView;
  onChange: (view: CourseView) => void;
}

/** Segmented Learn | Map control for the canvas header. Switches a ready course between the lesson
 *  reader and the prerequisite-graph explorer. A radiogroup with the APG roving-tabindex + arrow-key
 *  pattern: only the active option is tabbable, and Left/Right (or Up/Down) move the selection. */
export function ViewToggle({ value, onChange }: ViewToggleProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const isForward = event.key === "ArrowRight" || event.key === "ArrowDown";
    const isBackward = event.key === "ArrowLeft" || event.key === "ArrowUp";
    if (!isForward && !isBackward) return;
    event.preventDefault();
    const offset = isForward ? 1 : -1;
    const next = (index + offset + OPTIONS.length) % OPTIONS.length;
    onChange(OPTIONS[next]!.value);
    refs.current[next]?.focus();
  };

  return (
    <div className={styles.toggle} role="radiogroup" aria-label="Course view">
      {OPTIONS.map((option, index) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            className={`${styles.option} ${active ? styles.active : ""}`}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
