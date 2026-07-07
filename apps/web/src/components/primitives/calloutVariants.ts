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
