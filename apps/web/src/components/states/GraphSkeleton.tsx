import styles from "./DataStates.module.css";

// Loose top-to-bottom arrangement that echoes a small prerequisite DAG.
const PLACEHOLDERS = [
  { top: "8%", left: "38%" },
  { top: "34%", left: "20%" },
  { top: "34%", left: "56%" },
  { top: "62%", left: "40%" },
  { top: "84%", left: "40%" },
];

/** Skeleton that matches the final graph layout (per enterprise-ui: no centered spinner). */
export function GraphSkeleton() {
  return (
    <div className={styles.skeleton} role="status" aria-label="Loading prerequisite graph…">
      {PLACEHOLDERS.map((pos) => (
        <div
          key={`${pos.top}-${pos.left}`}
          className={styles.skeletonNode}
          style={{ top: pos.top, left: pos.left }}
        />
      ))}
      <span className="sr-only">Loading prerequisite graph…</span>
    </div>
  );
}
