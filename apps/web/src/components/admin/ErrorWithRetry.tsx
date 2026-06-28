import { Button } from "../primitives/Button";
import styles from "./AdminPortal.module.css";

/** An inline error message with a Retry action, shared across the prod-operations admin sections. */
export function ErrorWithRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.statusRegion}>
      <p className={styles.error} role="alert">
        {message}
      </p>
      <div>
        <Button type="button" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </div>
  );
}
