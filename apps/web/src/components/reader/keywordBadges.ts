import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

import { KEYWORD_META } from "./keywordMeta";

/** Render-side rule that visualises attention-worthy inline tokens as labelled chips:
 *  - recognised domain keywords (today: HTTP request methods) → a category-toned badge,
 *  - phonetic/symbol notation in slashes (`/p/`, `/ʃ/`) → a "symbol" chip, and
 *  - domain/data tokens recognised by SHAPE — identifiers with an internal digit (`IL-4`, `Th2`,
 *    `ILC2`), all-caps acronyms (`TSLP`, `DNA`), mixed-case tokens (`IgE`, `mRNA`), and hyphenated
 *    number-units (`600-eosinophil`) → a neutral "data" chip ("data is the typographic signature").
 *  It rewrites only whole-word, exact-case occurrences and tightly-bounded tokens in plain prose — so
 *  "DELETE" is badged but "delete" is not, "/p/" is tagged but "path/to/x" and "12/25/2024" are not,
 *  and a bare year ("2024") or an all-caps emphasis word ("REALLY") is left alone. Link text and
 *  existing badges are skipped, and inline code is untouched for free (its content isn't a text
 *  node). Section labels are already lowered to `seclabel` before this runs, so their words are
 *  attributes, never chipped. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

const KEYWORDS = Object.keys(KEYWORD_META);

/** Data-token shapes (see the module doc). Ordered so an identifier-with-digit wins over the bare
 *  acronym rule (`ILC2` chips whole, not `ILC` + stray `2`). */
const DATA_TOKEN =
  "[A-Z][A-Za-z]*-?\\d[\\dA-Za-z]*" + // internal-digit id: IL-4, IL-33, Th2, ILC2, CO2, T2
  "|[A-Z]{3,5}" + // all-caps acronym: TSLP, DNA, ICS (≤5 so English words like GETTING don't chip)
  "|[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*" + // mixed-case token: IgE, mRNA, pH, IPv4
  "|\\d+-[a-z][a-z-]{2,}"; // hyphenated number-unit: 600-eosinophil, 5-year

/** All-caps English words that read as emphasis, not acronyms — excluded from the acronym shape. */
const STOP_TOKENS = new Set([
  "THE", "AND", "BUT", "FOR", "NOT", "YOU", "ARE", "ALL", "ANY", "CAN", "HAS", "HOW", "WHY", "WHO",
  "WAS", "USE", "NOW", "OUR", "OUT", "ONE", "TWO", "VERY", "MUST", "ONLY", "ALSO", "THIS", "THAT",
  "WITH", "FROM", "INTO", "THAN", "THEN", "THEY", "WHEN", "EACH", "MORE", "SOME", "WHAT", "YES",
  "REALLY", "NEVER", "ALWAYS", "HERE", "THERE", "THESE", "THOSE", "WILL", "WOULD", "SHOULD",
]);

// A keyword (group 1) OR a slash-delimited symbol of 1–2 non-digit chars bounded by space/punctuation
// (group 2) OR a shape-recognised data token (group 3). The symbol guard excludes paths and dates.
const TOKEN_PATTERN = new RegExp(
  `\\b(${KEYWORDS.join("|")})\\b|(?<=^|[\\s(])\\/([^\\s/0-9]{1,2})\\/(?=$|[\\s).,;:])|\\b(${DATA_TOKEN})\\b`,
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
        } else if (match[3] !== undefined) {
          // A shape-recognised data token — unless it's a common all-caps word (emphasis, not an
          // acronym), in which case it stays plain text.
          if (STOP_TOKENS.has(match[3].toUpperCase())) {
            replacement.push({ type: "text", value: match[0] });
          } else {
            replacement.push(badge(match[3], "data"));
          }
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
