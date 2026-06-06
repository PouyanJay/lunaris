import type { ReactNode } from "react";

import { KEYWORD_META } from "./keywordMeta";
import styles from "./KeywordBadge.module.css";

interface KeywordBadgeProps {
  /** The badge category (tone), lowered from the keyword registry. */
  category?: string;
  children?: ReactNode;
}

/** A recognised keyword rendered as a monospace chip toned by its category. The keyword text stays
 *  the accessible label; the category tone is decorative reinforcement, and a title gives the
 *  longhand on hover. */
export function KeywordBadge({ category, children }: KeywordBadgeProps) {
  const text = typeof children === "string" ? children : "";
  const meta = KEYWORD_META[text];
  return (
    <span
      className={`${styles.badge} mono`}
      data-category={category ?? meta?.category ?? "default"}
      title={meta?.title ?? undefined}
    >
      {children}
    </span>
  );
}
