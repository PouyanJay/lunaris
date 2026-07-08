import styles from "./SearchTrigger.module.css";

interface SearchTriggerProps {
  onOpen: () => void;
}

/** The topbar's search field — really a button that opens the ⌘K palette (the design's
 *  "Search courses, concepts, sources…" affordance). The words collapse on narrow screens
 *  (CSS); the shortcut hint is decorative — the real label names the action. */
export function SearchTrigger({ onOpen }: SearchTriggerProps) {
  return (
    <button type="button" className={styles.trigger} aria-label="Search (⌘K)" onClick={onOpen}>
      <svg
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
      <span className={styles.placeholder}>Search courses, lessons, concepts…</span>
      <kbd className={`${styles.hint} mono`} aria-hidden="true">
        ⌘K
      </kbd>
    </button>
  );
}
