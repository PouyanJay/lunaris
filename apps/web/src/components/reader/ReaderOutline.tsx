import styles from "./ReaderOutline.module.css";

/** One lesson entry in the outline; `index` is its position in the flattened course-wide lesson
 *  order (the value the reader focuses on). */
export interface OutlineItem {
  index: number;
  label: string;
}

/** A module and its lessons in the outline. */
export interface OutlineGroup {
  moduleId: string;
  moduleTitle: string;
  items: OutlineItem[];
}

interface ReaderOutlineProps {
  groups: OutlineGroup[];
  activeIndex: number;
  onSelect: (index: number) => void;
}

/** The course outline (TOC): lessons grouped under their module titles. The active lesson is marked
 *  `aria-current`; each entry is a button so the outline is fully keyboard-operable. */
export function ReaderOutline({ groups, activeIndex, onSelect }: ReaderOutlineProps) {
  return (
    <nav className={styles.outline} aria-label="Course outline">
      {groups.map((group) => (
        <div key={group.moduleId} className={styles.group}>
          <p className={`eyebrow ${styles.groupTitle}`}>{group.moduleTitle}</p>
          <ul className={styles.items}>
            {group.items.map((item) => {
              const active = item.index === activeIndex;
              return (
                <li key={item.index}>
                  <button
                    type="button"
                    className={`${styles.item} ${active ? styles.active : ""}`}
                    aria-current={active ? "page" : undefined}
                    onClick={() => onSelect(item.index)}
                  >
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
