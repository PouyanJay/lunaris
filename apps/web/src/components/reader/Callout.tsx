import type { ReactNode } from "react";

import styles from "./Callout.module.css";

/** The admonition variants the authoring model can emit (via `:::note` … or a "Note:" lead-in). */
export type CalloutVariant = "note" | "tip" | "insight" | "warning" | "example" | "key-takeaway";

interface CalloutMeta {
  label: string;
  glyph: string;
}

const META: Record<CalloutVariant, CalloutMeta> = {
  note: { label: "Note", glyph: "›" },
  tip: { label: "Tip", glyph: "✦" },
  insight: { label: "Insight", glyph: "◆" },
  warning: { label: "Warning", glyph: "▲" },
  example: { label: "Example", glyph: "❯" },
  "key-takeaway": { label: "Key takeaway", glyph: "★" },
};

interface CalloutProps {
  variant?: string;
  children?: ReactNode;
}

function resolve(variant?: string): CalloutVariant {
  return variant && variant in META ? (variant as CalloutVariant) : "note";
}

/** An admonition panel — hairline-bordered with a tinted spine, a glyph + text label (the meaning is
 *  carried by the word and glyph, never colour alone) and the prose body. Reused for every variant so
 *  the box style lives in one place. */
export function Callout({ variant, children }: CalloutProps) {
  const kind = resolve(variant);
  const meta = META[kind];
  return (
    <aside className={styles.callout} data-variant={kind} aria-label={meta.label}>
      <p className={styles.label}>
        <span className={styles.glyph} aria-hidden="true">
          {meta.glyph}
        </span>
        {meta.label}
      </p>
      <div className={styles.body}>{children}</div>
    </aside>
  );
}
