import type { ExplainAnswerSource } from "./ExplainContext";
import type { ExplainState } from "./useExplain";
import styles from "./ExplainResult.module.css";

interface ExplainResultProps {
  state: ExplainState;
}

/** The badge wording per answering tier — mono-uppercase per the house status convention. */
const SOURCE_LABELS: Record<ExplainAnswerSource, string> = {
  hosted: "CLAUDE",
  "server-fallback": "LUNARIS SERVER",
  "on-device": "YOUR DEVICE",
};

/** The outcome strip under a block that was asked to explain itself: the model download's
 *  determinate progress (on-device first run), the explanation with its answering-tier badge,
 *  or the failure (announced, recoverable — the Explain button stays). Idle/loading render
 *  nothing; the trigger button carries the loading state. */
export function ExplainResult({ state }: ExplainResultProps) {
  if (state.status === "downloading") {
    const percent = Math.round(state.progress * 100);
    return (
      <div className={styles.result} role="status">
        <span className="eyebrow">Preparing on-device model</span>
        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Model download"
        >
          <div className={styles.progressFill} style={{ width: `${percent}%` }} />
        </div>
        <p className={styles.body}>{state.text}</p>
      </div>
    );
  }
  if (state.status === "done") {
    return (
      <div className={styles.result} role="status">
        <span className={styles.head}>
          <span className="eyebrow">Explanation</span>
          <span className={`mono ${styles.badge}`} data-source={state.source}>
            {SOURCE_LABELS[state.source]}
          </span>
        </span>
        <p className={styles.body}>{state.explanation}</p>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className={`${styles.result} ${styles.error}`} role="alert">
        <p className={styles.body}>{state.message}</p>
      </div>
    );
  }
  return null;
}
