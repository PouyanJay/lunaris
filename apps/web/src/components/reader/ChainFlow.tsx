import type { ReactNode } from "react";

import styles from "./ChainFlow.module.css";

interface ChainFlowProps {
  /** Node count, lowered from the transform — used only for the accessible label. */
  count?: string;
  children?: ReactNode;
}

/** An inline process chain ("A → B → C") lifted from prose into a numbered, ordered flow. Real <ol>
 *  semantics carry the step order for assistive tech; the arrow connectors between chips are
 *  CSS-drawn decoration. On narrow screens the row stacks and the arrows rotate to point down. */
export function ChainFlow({ count, children }: ChainFlowProps) {
  const steps = count ?? "";
  return (
    <ol className={styles.flow} aria-label={`${steps}-step chain`.replace(/^-/, "")}>
      {children}
    </ol>
  );
}

/** One node of the chain (an <li>); the step number is a CSS counter, so it never enters the text. */
export function ChainNode({ children }: { children?: ReactNode }) {
  return (
    <li className={styles.node}>
      <span className={styles.body}>{children}</span>
    </li>
  );
}
