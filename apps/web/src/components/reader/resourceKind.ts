import type { ResourceKind } from "../../types/course";

/** Short mono glyph per resource kind — the type marker used on resource cards (the fallback tile in
 *  ResourceThumb, and the leading badge on a chapter's docked resource in the Cinema rail). Shared so
 *  the two surfaces label a kind identically. */
export const KIND_GLYPH: Record<ResourceKind, string> = {
  video: "VIDEO",
  article: "READ",
  docs: "DOCS",
  practice: "TRY",
  tool: "TOOL",
  reference: "REF",
};
