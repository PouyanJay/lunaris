import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

import { KEYWORD_META } from "./keywordMeta";

/** Render-side rule that visualises attention-worthy inline tokens as labelled chips:
 *  - recognised domain keywords (today: HTTP request methods) → a category-toned badge, and
 *  - phonetic/symbol notation in slashes (`/p/`, `/ʃ/`) → a "symbol" chip.
 *  It rewrites only whole-word, exact-case keyword occurrences and tightly-bounded symbol tokens in
 *  plain prose — so the uppercase "DELETE" is badged but the word "delete" is not, and "/p/" is
 *  tagged but "path/to/x" and "12/25/2024" are not. Link text and existing badges are left alone, and
 *  inline code is untouched for free (its content isn't a text node). */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

const KEYWORDS = Object.keys(KEYWORD_META);
// A keyword (group 1) OR a slash-delimited symbol of 1–2 non-digit chars bounded by space/punctuation
// (group 2). The symbol guard excludes paths and dates.
const TOKEN_PATTERN = new RegExp(
  `\\b(${KEYWORDS.join("|")})\\b|(?<=^|[\\s(])\\/([^\\s/0-9]{1,2})\\/(?=$|[\\s).,;:])`,
  "g",
);

/** An inline chip element (carried on `emphasis`, whose tag we override to `keyword` via hName). */
function badge(text: string, category: string): Node {
  return {
    type: "emphasis",
    data: { hName: "keyword", hProperties: { category } },
    children: [{ type: "text", value: text }],
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
      const matches = [...value.matchAll(TOKEN_PATTERN)];
      if (matches.length === 0) return;

      const replacement: Node[] = [];
      let last = 0;
      for (const match of matches) {
        const at = match.index ?? 0;
        if (at > last) replacement.push({ type: "text", value: value.slice(last, at) });
        if (match[1] !== undefined) {
          replacement.push(badge(match[1], KEYWORD_META[match[1]]!.category));
        } else {
          replacement.push(badge(match[0], "symbol"));
        }
        last = at + match[0].length;
      }
      if (last < value.length) replacement.push({ type: "text", value: value.slice(last) });

      owner.children!.splice(index, 1, ...replacement);
      return [SKIP, index + replacement.length];
    });
  };
}

export { remarkKeywordBadges };
