import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import { Button } from "../primitives/Button";
import { relativeTime } from "../../lib/relativeTime";
import type { RunsState } from "../../hooks/useRuns";
import type { CourseRun, RunStatus } from "../../types/course";
import styles from "./RunList.module.css";

/** Run lifecycle → the house status convention (dot + uppercase-mono label). Only RUNNING is live. */
const STATUS_TONE: Record<RunStatus, { tone: StatusTone; live: boolean }> = {
  running: { tone: "accent", live: true },
  completed: { tone: "success", live: false },
  failed: { tone: "danger", live: false },
};

const SKELETON_ROW_COUNT = 3;

interface RunListProps {
  state: RunsState;
  onRetry: () => void;
  /** When provided, runs render as buttons that open the course. */
  onSelectRun?: ((run: CourseRun) => void) | undefined;
  /** When provided, a non-running run shows a hover/focus-revealed delete action. */
  onDeleteRun?: ((run: CourseRun) => void) | undefined;
  selectedRunId?: string | undefined;
}

/** The sidebar's run-history feed with all data states: loading (skeleton rows), error (retry),
 *  empty (hint to start one), and the loaded list. */
export function RunList({
  state,
  onRetry,
  onSelectRun,
  onDeleteRun,
  selectedRunId,
}: RunListProps) {
  if (state.status === "loading") {
    return (
      <div className={styles.list} role="status" aria-label="Loading run history…">
        {Array.from({ length: SKELETON_ROW_COUNT }, (_, row) => (
          <div key={row} className={styles.skeletonRow} aria-hidden="true" />
        ))}
        <span className="sr-only">Loading run history…</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.notice} role="alert">
        <p className={styles.noticeText}>{state.message}</p>
        <Button onClick={onRetry}>Retry</Button>
      </div>
    );
  }

  if (state.runs.length === 0) {
    return (
      <div className={styles.notice}>
        <p className={styles.noticeText}>No runs yet. Start one with “New course”.</p>
      </div>
    );
  }

  return (
    <ul className={styles.list}>
      {state.runs.map((run) => (
        <li key={run.id}>
          <RunItem
            run={run}
            onSelect={onSelectRun}
            onDelete={onDeleteRun}
            selected={run.id === selectedRunId}
          />
        </li>
      ))}
    </ul>
  );
}

interface RunItemProps {
  run: CourseRun;
  onSelect?: ((run: CourseRun) => void) | undefined;
  onDelete?: ((run: CourseRun) => void) | undefined;
  selected: boolean;
}

function RunItem({ run, onSelect, onDelete, selected }: RunItemProps) {
  const { tone, live } = STATUS_TONE[run.status];
  const itemClass = `${styles.item} ${selected ? styles.itemSelected : ""}`.trim();
  // Counts live in the canvas metric band when a course is open; the narrow rail shows status +
  // time (the count tooltip keeps them one hover away without truncating every row).
  const tooltip = `${run.topic} — ${run.kcCount} KC, ${run.moduleCount} modules`;
  const body = (
    <>
      <span className={styles.topic} title={tooltip}>
        {run.topic}
      </span>
      <span className={styles.meta}>
        <StatusDot label={run.status} tone={tone} live={live} />
        <span className={`mono ${styles.metaText}`}>{relativeTime(run.createdAt)}</span>
      </span>
    </>
  );

  // Offline / non-interactive: a static row with no actions.
  if (!onSelect) {
    return <div className={itemClass}>{body}</div>;
  }

  // A running run has no deletable assets yet (the API 409s), so we don't offer the action for it.
  // Testing onDelete inline (not via a derived boolean) lets TypeScript narrow it to non-null below.
  return (
    <div className={itemClass}>
      <button
        type="button"
        className={styles.select}
        onClick={() => onSelect(run)}
        aria-current={selected ? "page" : undefined}
      >
        {body}
      </button>
      {onDelete !== undefined && run.status !== "running" && (
        <button
          type="button"
          className={styles.delete}
          onClick={() => onDelete(run)}
          aria-label={`Delete course: ${run.topic}`}
          title="Delete course"
        >
          <TrashIcon />
        </button>
      )}
    </div>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M2.5 4h11M6.5 4V2.75A.75.75 0 0 1 7.25 2h1.5a.75.75 0 0 1 .75.75V4m2 0v8.25a1.25 1.25 0 0 1-1.25 1.25h-5.5A1.25 1.25 0 0 1 4 12.25V4M6.5 7v4M9.5 7v4"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
