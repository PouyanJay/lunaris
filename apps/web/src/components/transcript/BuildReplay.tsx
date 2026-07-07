import { Button } from "../primitives/Button";
import { BuildTimeline } from "./BuildTimeline";
import { useRunTrace } from "../../hooks/useRunTrace";
import states from "../states/DataStates.module.css";
import styles from "./BuildReplay.module.css";

// Skeleton rows that echo a timeline spine (the CSS varies their widths via nth-child).
const SKELETON_ROWS = [0, 1, 2, 3];

interface BuildReplayProps {
  apiBaseUrl: string;
  /** The run whose persisted log to replay. Absent for a course with no recorded build → empty. */
  runId: string | undefined;
  topic: string;
}

/**
 * The Build tab: replays a past run's persisted event log into the same `BuildTimeline` the live
 * build streams into, but static — no SSE. Covers every data state (loading / empty / error /
 * loaded); a course built before build sessions were recorded shows a calm "no build record" state.
 */
export function BuildReplay({ apiBaseUrl, runId, topic }: BuildReplayProps) {
  const { state, reload } = useRunTrace(apiBaseUrl, runId);

  if (state.status === "loading") {
    return (
      <div className={styles.skeleton} role="status" aria-label="Loading build record…">
        {SKELETON_ROWS.map((row) => (
          <div key={row} className={styles.skeletonRow}>
            <span className={styles.skeletonDot} />
            <span className={styles.skeletonLine} />
          </div>
        ))}
      </div>
    );
  }

  if (state.status === "empty") {
    return (
      <div className={states.center}>
        <div className={states.message}>
          <span className="eyebrow">Build record</span>
          <h2 className={states.title}>No build record</h2>
          <p className={states.body}>
            This course was built before build sessions were recorded, so there&rsquo;s no timeline
            to replay. New builds are captured automatically — use Lessons or Map to explore this
            course.
          </p>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={states.center}>
        <div className={states.message} role="alert">
          <span className="eyebrow">Build record</span>
          <h2 className={states.title}>Couldn&rsquo;t load the build record</h2>
          <p className={states.body}>{state.message}</p>
          <div className={states.action}>
            <Button variant="primary" onClick={reload}>
              Try again
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return <BuildTimeline topic={topic} events={state.events} agentEvents={state.agentEvents} />;
}
