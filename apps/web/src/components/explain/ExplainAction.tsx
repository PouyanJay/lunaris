import { isValidElement, type ReactNode } from "react";

import { ExplainResult } from "./ExplainResult";
import { useExplain } from "./useExplain";
import styles from "./ExplainAction.module.css";

/** Flatten rendered markdown children to the plain prose the model should explain. Element props
 *  other than children (hrefs, classNames) are presentation, not content, and are dropped. */
export function reactNodeToText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(reactNodeToText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return reactNodeToText(node.props.children);
  return "";
}

interface ExplainActionProps {
  /** The plain text to explain (callers usually flatten children via reactNodeToText). */
  content: string;
  /** A short steer for the model, e.g. the block's kind ("insight callout"). */
  context?: string;
}

/** A self-contained "Explain" footer for any reader block: the trigger (with its in-flight label)
 *  plus the shared result strip. Renders nothing when the capability is unavailable or the block
 *  has no extractable text. */
export function ExplainAction({ content, context }: ExplainActionProps) {
  const { available, state, explain } = useExplain();
  if (!available || content.trim() === "") return null;
  const isExplaining = state.status === "loading" || state.status === "downloading";

  return (
    <div className={styles.action}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => void explain(content, context)}
        disabled={isExplaining}
        aria-live="polite"
      >
        {isExplaining ? "Explaining…" : "Explain"}
      </button>
      <ExplainResult state={state} />
    </div>
  );
}
