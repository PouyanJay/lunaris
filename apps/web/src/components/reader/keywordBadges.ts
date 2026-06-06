import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

import { KEYWORD_META } from "./keywordMeta";

/** Render-side rule that visualises recognised domain keywords (today: HTTP request methods) as
 *  labelled chips. It rewrites only whole-word, exact-case occurrences in plain prose text — so the
 *  uppercase "DELETE" in "DELETE removes a resource" becomes a badge while the ordinary word "delete"
 *  never does — and it leaves link text and existing badges alone. Inline code is untouched for free
 *  (its content isn't a text node). */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

const KEYWORDS = Object.keys(KEYWORD_META);
const KEYWORD_PATTERN = new RegExp(`\\b(${KEYWORDS.join("|")})\\b`, "g");

/** An inline keyword badge element (carried on `emphasis`, whose tag we override via hName). */
function badge(keyword: string): Node {
  return {
    type: "emphasis",
    data: { hName: "keyword", hProperties: { category: KEYWORD_META[keyword]!.category } },
    children: [{ type: "text", value: keyword }],
  };
}

function remarkKeywordBadges() {
  return (tree: Root): void => {
    visit(tree, "text", (node, index, parent) => {
      if (index === undefined || !parent) return;
      const owner = parent as unknown as Node;
      // Don't badge inside links or inside an already-lowered badge.
      if (owner.type === "link" || owner.data?.hName === "keyword") return;

      const value = (node as unknown as Node).value ?? "";
      const matches = [...value.matchAll(KEYWORD_PATTERN)];
      if (matches.length === 0) return;

      const replacement: Node[] = [];
      let last = 0;
      for (const match of matches) {
        const at = match.index ?? 0;
        if (at > last) replacement.push({ type: "text", value: value.slice(last, at) });
        replacement.push(badge(match[1]!));
        last = at + match[0].length;
      }
      if (last < value.length) replacement.push({ type: "text", value: value.slice(last) });

      owner.children!.splice(index, 1, ...replacement);
      return [SKIP, index + replacement.length];
    });
  };
}

export { remarkKeywordBadges };
