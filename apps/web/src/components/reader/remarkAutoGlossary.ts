import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

/** Glossary propagation (Field Guide): the first plain-prose occurrence of an indexed term in a
 *  rendered tree becomes a hoverable glossary node, so a concept defined once (in the course
 *  graph or an authored `:term`) is explorable wherever it reappears. Only prose-level text is
 *  rewritten — links, code, headings, and existing directives are left alone — and a term the
 *  author already marked in the same tree is never doubled up. */

interface Node {
  type: string;
  name?: string;
  value?: string;
  children?: Node[];
  attributes?: Record<string, string>;
  data?: Record<string, unknown>;
}

/** Parents whose direct text children read as running prose. */
const PROSE_PARENTS = new Set(["paragraph", "listItem", "emphasis", "strong", "tableCell"]);

const GLOSSARY_DIRECTIVES = new Set(["term", "def"]);

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function glossaryNode(text: string, definition: string): Node {
  return {
    type: "textDirective",
    name: "term",
    attributes: { title: definition },
    children: [{ type: "text", value: text }],
    // Pre-lowered so this plugin composes independently of the directive-lowering pass.
    data: { hName: "glossary", hProperties: { definition } },
  };
}

function remarkAutoGlossary(options: { index: ReadonlyMap<string, string> }) {
  const { index } = options;
  return (tree: Root): void => {
    if (index.size === 0) return;
    // Longest term first, so "binary search tree" beats "binary search" at the same position.
    const terms = [...index.keys()].sort((a, b) => b.length - a.length);
    const pattern = new RegExp(`\\b(?:${terms.map(escapeRegExp).join("|")})\\b`, "gi");

    // One mark per term per tree — and an authored :term counts as that one mark.
    const seen = new Set<string>();
    visit(tree, (node) => {
      const directive = node as unknown as Node;
      if (
        (directive.type === "textDirective" || directive.type === "leafDirective") &&
        directive.name &&
        GLOSSARY_DIRECTIVES.has(directive.name)
      ) {
        const text = (directive.children ?? [])
          .map((child) => child.value ?? "")
          .join("")
          .trim()
          .toLowerCase();
        if (text) seen.add(text);
      }
    });

    visit(tree, "text", (node, indexInParent, parent) => {
      if (indexInParent === undefined || !parent) return;
      const owner = parent as unknown as Node;
      if (!PROSE_PARENTS.has(owner.type)) return;

      const value = (node as unknown as Node).value ?? "";
      pattern.lastIndex = 0;
      const replacement: Node[] = [];
      let cursor = 0;
      let match: RegExpExecArray | null;
      while ((match = pattern.exec(value))) {
        const key = match[0].toLowerCase();
        const definition = index.get(key);
        if (!definition || seen.has(key)) continue;
        seen.add(key);
        if (match.index > cursor) {
          replacement.push({ type: "text", value: value.slice(cursor, match.index) });
        }
        replacement.push(glossaryNode(match[0], definition));
        cursor = match.index + match[0].length;
      }
      if (replacement.length === 0) return;
      if (cursor < value.length) replacement.push({ type: "text", value: value.slice(cursor) });

      owner.children!.splice(indexInParent, 1, ...replacement);
      return [SKIP, indexInParent + replacement.length];
    });
  };
}

export { remarkAutoGlossary };
