/** One run of caption text, flagged when it is a chapter key term (rendered with emphasis). */
export interface TextSegment {
  text: string;
  highlight: boolean;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Split a caption line into segments, flagging the runs that match one of the chapter's key terms
 *  (whole-word, case-insensitive; multi-word phrases match as a phrase). Deterministic and
 *  loss-less — concatenating the segments' text reproduces the input. No terms (or none present) →
 *  a single unhighlighted segment. */
export function highlightTerms(text: string, terms: string[]): TextSegment[] {
  const cleaned = terms.map((term) => term.trim()).filter(Boolean);
  if (cleaned.length === 0) return text ? [{ text, highlight: false }] : [];

  // Longest first so a phrase ("characteristic length") wins over its component words.
  const alternation = [...cleaned]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  const pattern = new RegExp(`\\b(?:${alternation})\\b`, "gi");

  const segments: TextSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ text: text.slice(last, start), highlight: false });
    segments.push({ text: match[0], highlight: true });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), highlight: false });
  return segments;
}
