import { BuildControlRoom } from "../controlroom/BuildControlRoom";
import { Button } from "../primitives/Button";
import { useLiveRunTrace } from "../../hooks/useLiveRunTrace";
import states from "../states/DataStates.module.css";
import styles from "./BuildReplay.module.css";

// Skeleton rows that echo a timeline spine (the CSS varies their widths via nth-child).
const SKELETON_ROWS = [0, 1, 2, 3];

interface LiveBuildReplayProps {
  apiBaseUrl: string;
  /** The in-flight run whose live log to reattach to. */
  runId: string;
  topic: string;
}

/**
 * Reattaches a still-running build to its live view: polls the run's persisted event log and
 * renders it into the same control room the live SSE streams into — so returning to an
 * in-progress run (reload / navigate / a dropped stream) shows live progress, not a static "still
 * building" placeholder. The parent advances the canvas to the finished course once the run
 * completes (see `useOpenedRun`'s auto re-check), at which point this view is replaced.
 */
export function LiveBuildReplay({ apiBaseUrl, runId, topic }: LiveBuildReplayProps) {
  const { state, reload } = useLiveRunTrace(apiBaseUrl, runId);

  if (state.status === "loading") {
    return (
      <div className={styles.skeleton} role="status" aria-label="Reattaching to the live build…">
        {SKELETON_ROWS.map((row) => (
          <div key={row} className={styles.skeletonRow}>
            <span className={styles.skeletonDot} />
            <span className={styles.skeletonLine} />
          </div>
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={states.center}>
        <div className={states.message} role="alert">
          <span className="eyebrow">Live build</span>
          <h2 className={states.title}>Couldn&rsquo;t reach this build</h2>
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

  // An empty log just means the run hasn't emitted yet — the control room renders the pending
  // pipeline, which fills in as polls land, so there's no separate "nothing yet" state to show.
  return (
    <BuildControlRoom
      topic={topic}
      events={state.events}
      agentEvents={state.agentEvents}
      complete={state.events.some((event) => event.stage === "run_completed")}
    />
  );
}
