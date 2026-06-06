import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

/** Inline highlight: `==text==` becomes a `<mark>`, the standard "draw attention here" element. A
 *  cheap, explicit way for the author/model to spotlight a phrase or symbol. Only plain prose text is
 *  rewritten (link text and existing marks are skipped; inline code is untouched for free). */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string };
}

const HIGHLIGHT_PATTERN = /==([^=]+)==/g;

function mark(text: string): Node {
  return { type: "emphasis", data: { hName: "mark" }, children: [{ type: "text", value: text }] };
}

function remarkHighlight() {
  return (tree: Root): void => {
    visit(tree, "text", (node, index, parent) => {
      if (index === undefined || !parent) return;
      const owner = parent as unknown as Node;
      if (owner.type === "link" || owner.data?.hName === "mark") return;

      const value = (node as unknown as Node).value ?? "";
      const matches = [...value.matchAll(HIGHLIGHT_PATTERN)];
      if (matches.length === 0) return;

      const replacement: Node[] = [];
      let last = 0;
      for (const match of matches) {
        const at = match.index ?? 0;
        if (at > last) replacement.push({ type: "text", value: value.slice(last, at) });
        replacement.push(mark(match[1]!));
        last = at + match[0].length;
      }
      if (last < value.length) replacement.push({ type: "text", value: value.slice(last) });

      owner.children!.splice(index, 1, ...replacement);
      return [SKIP, index + replacement.length];
    });
  };
}

export { remarkHighlight };
