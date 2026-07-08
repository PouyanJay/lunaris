import styles from "./FilterPills.module.css";

export interface FilterPillOption<T extends string> {
  value: T;
  label: string;
}

interface FilterPillsProps<T extends string> {
  options: FilterPillOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** The group's accessible name (e.g. "Filter courses"). */
  label: string;
}

/** The mono filter-pill row — one source of truth for the motif the library and bookmarks share
 *  (the SegmentedControl's generic API, in pill clothes). Pressed state = the active filter. */
export function FilterPills<T extends string>({
  options,
  value,
  onChange,
  label,
}: FilterPillsProps<T>) {
  return (
    <div className={styles.pills} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={styles.pill}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
