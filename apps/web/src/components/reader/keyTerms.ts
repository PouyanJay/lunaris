import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

/** Authored prose names its key concept with a definitional statement — "Airway inflammation is the
 *  hallmark feature of asthma." This remark transform bolds the SUBJECT of such a statement so the
 *  defined term stands out. Presentation-only (it only wraps existing words in `strong`). Deliberately
 *  rare: it fires only when the predicate opens with a strong definitional cue word ("hallmark",
 *  "defining", "dominant", …), and only on the sentence subject (≤5 words at a sentence start), so
 *  ordinary "X is a/the …" prose keeps no emphasis and bold stays meaningful. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string };
}

/** Definitional cue adjectives — kept tight (no "key"/"core"/"main", which read as ordinary prose). */
const CUE = "hallmark|defining|dominant|central|primary|principal|chief|cornerstone|essential|fundamental";
/** A subject (≤5 words, sentence-initial) followed by "is/are (the|a|an) <cue>". */
const DEFINITION = new RegExp(
  `(^|[.!?]\\s+)([A-Z][\\w-]*(?:\\s+[\\w-]+){0,4}?)\\s+(?:is|are)\\s+(?:the|a|an)\\s+(?:${CUE})\\b`,
);

/** A `strong` node wrapping the subject text. */
function strong(value: string): Node {
  return { type: "strong", children: [{ type: "text", value }] };
}

/** Remark transform: within plain paragraph text, bold the subject of the first definitional
 *  statement found in a text node. */
function remarkKeyTerms() {
  return (tree: Root): void => {
    visit(tree, "text", (node, index, parent) => {
      if (index === undefined || !parent) return;
      const owner = parent as unknown as Node;
      // Only touch running prose — never link text, existing emphasis, or a lowered custom element.
      if (owner.type === "link" || owner.type === "strong" || owner.type === "emphasis") return;
      if (owner.data?.hName) return;

      const value = (node as unknown as Node).value ?? "";
      const match = value.match(DEFINITION);
      if (!match || match.index === undefined) return;

      const subjectStart = match.index + match[1]!.length;
      const subjectEnd = subjectStart + match[2]!.length;

      const replacement: Node[] = [];
      const before = value.slice(0, subjectStart);
      if (before) replacement.push({ type: "text", value: before });
      replacement.push(strong(value.slice(subjectStart, subjectEnd)));
      const after = value.slice(subjectEnd);
      if (after) replacement.push({ type: "text", value: after });

      owner.children!.splice(index, 1, ...replacement);
      return [SKIP, index + replacement.length];
    });
  };
}

export { remarkKeyTerms };
