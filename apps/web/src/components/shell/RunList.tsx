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
  /** When provided, runs render as buttons that open the course (wired in a later task). */
  onSelectRun?: ((run: CourseRun) => void) | undefined;
  selectedRunId?: string | undefined;
}

/** The sidebar's run-history feed with all data states: loading (skeleton rows), error (retry),
 *  empty (hint to start one), and the loaded list. */
export function RunList({ state, onRetry, onSelectRun, selectedRunId }: RunListProps) {
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
          <RunItem run={run} onSelect={onSelectRun} selected={run.id === selectedRunId} />
        </li>
      ))}
    </ul>
  );
}

interface RunItemProps {
  run: CourseRun;
  onSelect?: ((run: CourseRun) => void) | undefined;
  selected: boolean;
}

function RunItem({ run, onSelect, selected }: RunItemProps) {
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

  if (!onSelect) {
    return <div className={itemClass}>{body}</div>;
  }
  return (
    <button
      type="button"
      className={itemClass}
      onClick={() => onSelect(run)}
      aria-current={selected ? "page" : undefined}
    >
      {body}
    </button>
  );
}
