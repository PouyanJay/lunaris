import type { ExplainState } from "./useExplain";
import styles from "./ExplainResult.module.css";

interface ExplainResultProps {
  state: ExplainState;
}

/** The outcome strip under a block that was asked to explain itself: the explanation (announced
 *  politely), or the failure (announced assertively, recoverable — the Explain button stays).
 *  Renders nothing while idle; the loading state lives on the triggering button. */
export function ExplainResult({ state }: ExplainResultProps) {
  if (state.status === "done") {
    return (
      <div className={styles.result} role="status">
        <span className="eyebrow">Explanation</span>
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
