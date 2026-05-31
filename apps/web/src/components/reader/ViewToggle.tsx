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
 *  reader and the prerequisite-graph explorer. A radiogroup so the active view is announced; the
 *  global focus-visible ring handles keyboard affordance. */
export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div className={styles.toggle} role="radiogroup" aria-label="Course view">
      {OPTIONS.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            className={`${styles.option} ${active ? styles.active : ""}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
