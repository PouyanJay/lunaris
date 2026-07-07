import type { ReactNode } from "react";

import styles from "./Callout.module.css";
import { CALLOUT_META, resolveCalloutVariant } from "./calloutVariants";

interface CalloutProps {
  variant?: string | undefined;
  /** Optional trailing affordance rendered inside the panel (e.g. the reader's Explain action). */
  action?: ReactNode;
  children?: ReactNode;
}

/** An admonition panel — hairline-bordered with a tinted spine, a glyph + text label (the meaning
 *  is carried by the word and glyph, never colour alone) and the prose body. Reused for every
 *  variant so the box style lives in one place. */
export function Callout({ variant, action, children }: CalloutProps) {
  const kind = resolveCalloutVariant(variant);
  const meta = CALLOUT_META[kind];
  return (
    <aside className={styles.callout} data-variant={kind} aria-label={meta.label}>
      <p className={styles.label}>
        <span className={styles.glyph} aria-hidden="true">
          {meta.glyph}
        </span>
        {meta.label}
      </p>
      <div className={styles.body}>{children}</div>
      {action}
    </aside>
  );
}
