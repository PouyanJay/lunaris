import type { ReactNode } from "react";

import { Button } from "../primitives/Button";
import styles from "./DataStates.module.css";

interface CanvasNoticeProps {
  /** Uppercase-mono micro-label above the title (e.g. "404", "Restricted"). */
  eyebrow: string;
  title: string;
  body: ReactNode;
  actionLabel: string;
  onAction: () => void;
}

/** A designed full-canvas notice with a single recovery action — for navigation dead ends
 *  (unknown URL, restricted page) that must never render as a blank or broken canvas. */
export function CanvasNotice({ eyebrow, title, body, actionLabel, onAction }: CanvasNoticeProps) {
  return (
    <div className={styles.center}>
      <div className={styles.message}>
        <span className="eyebrow">{eyebrow}</span>
        <h2 className={styles.title}>{title}</h2>
        <p className={styles.body}>{body}</p>
        <div className={styles.action}>
          <Button variant="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
