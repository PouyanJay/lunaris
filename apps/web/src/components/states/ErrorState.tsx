import { Button } from "../primitives/Button";
import styles from "./DataStates.module.css";

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

/** Human-readable failure + a recovery path — never a raw stack trace or dead end. */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className={styles.center}>
      <div className={styles.message} role="alert">
        <span className="eyebrow">Couldn&rsquo;t load the graph</span>
        <h2 className={styles.title}>Something went wrong</h2>
        <p className={styles.body}>{message}</p>
        <div className={styles.action}>
          <Button variant="primary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      </div>
    </div>
  );
}
