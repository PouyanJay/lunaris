import type { ReactNode } from "react";

import styles from "./Callout.module.css";

/** The admonition variants the design system carries (authoring models emit them via
 *  `:::note` … directives or a "Note:" lead-in). */
export type CalloutVariant = "note" | "tip" | "insight" | "warning" | "example" | "key-takeaway";

interface CalloutMeta {
  label: string;
  glyph: string;
}

/** Label + glyph per variant — the word and glyph carry the meaning, never colour alone. */
export const CALLOUT_META: Record<CalloutVariant, CalloutMeta> = {
  note: { label: "Note", glyph: "›" },
  tip: { label: "Tip", glyph: "✦" },
  insight: { label: "Insight", glyph: "◆" },
  warning: { label: "Warning", glyph: "▲" },
  example: { label: "Example", glyph: "❯" },
  "key-takeaway": { label: "Key takeaway", glyph: "★" },
};

/** Model-emitted variants arrive as loose strings; anything unknown quietly falls back to note. */
export function resolveCalloutVariant(variant?: string): CalloutVariant {
  return variant && variant in CALLOUT_META ? (variant as CalloutVariant) : "note";
}

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
