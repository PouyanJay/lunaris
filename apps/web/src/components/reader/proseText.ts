/** Small text helpers shared by the prose-formatting remark transforms (R1/R3/R4/R6). Extracted so the
 *  identical logic can't drift between transforms — the same discipline `proseStructure.ts` follows
 *  with its shared `SECTION_WORDS`. */

/** A minimal structural view of an mdast node — enough for the helpers here; each transform keeps its
 *  own richer local `Node` shape, which is assignable to this. */
interface TextChild {
  type: string;
  value?: string;
}

/** The flat string of a node's children iff every child is a plain text node (the authored norm).
 *  Returns null when inline formatting (em/strong/links) is present, so a transform can fall back to
 *  leaving the paragraph untouched rather than risk mangling inline nodes. */
export function plainText(children: readonly TextChild[]): string | null {
  let out = "";
  for (const child of children) {
    if (child.type !== "text") return null;
    out += child.value ?? "";
  }
  return out;
}

/** Split flat text at "… . Next" boundaries — a sentence terminator followed by whitespace and a
 *  capital/digit (optionally behind an opening quote/bracket). Named distinctly from `claimMatch.ts`'s
 *  abbreviation-aware `splitSentences`; chunk-level lesson prose here doesn't need that guarding. */
export function splitAtSentenceBoundaries(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=["'“(]?[A-Z0-9])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}
