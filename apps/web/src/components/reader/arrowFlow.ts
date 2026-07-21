import type { Root } from "mdast";

/** Authored prose sometimes buries a process chain in a sentence — "the chain is trigger → epithelial
 *  TSLP/IL-33 → ILC2/Th2 activation → … → hyperresponsiveness." This remark transform lifts a run of
 *  ≥2 arrows (≥3 nodes) into a numbered flow (`chainflow` → an ordered list), keeping the lead-in and
 *  the trailing sentence as prose around it. Presentation-only: every node word is preserved verbatim;
 *  only the arrows and the one sentence terminator that closes the chain are dropped (structural
 *  punctuation, like the label colon in R1). Conservative: it needs ≥2 arrows, so a lone "A → B" and
 *  ordinary arrow-free prose are left untouched. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

/** Arrow separators: a Unicode arrow or an ASCII "->", with surrounding space. */
const ARROW = /\s*(?:→|->)\s*/g;
/** The lead-in ends at the last of: a sentence terminator / colon, or a chain cue word ("… is",
 *  "… are", "… follows", "chain", "sequence", "pathway", "route", "flow", "steps"). Everything after
 *  is the first node; everything before stays prose. */
const LEAD_BOUNDARY =
  /[.!?:]\s+|\b(?:is|are|follows|chain|sequence|pathway|route|flow|steps)\b\s+/gi;

/** The flat string of a paragraph iff every child is a plain text node (the authored norm). */
function plainText(children: Node[]): string | null {
  let out = "";
  for (const child of children) {
    if (child.type !== "text") return null;
    out += child.value ?? "";
  }
  return out;
}

interface Chain {
  lead: string;
  nodes: string[];
  trail: string;
}

/** Parse a paragraph's flat text into a chain (lead-in + nodes + trailing), or null when it holds no
 *  ≥3-node arrow run. */
function detectChain(text: string): Chain | null {
  const arrows = text.match(/→|->/g);
  if (!arrows || arrows.length < 2) return null;

  const firstArrow = text.search(/→|->/);

  // First node starts after the last lead boundary before the first arrow.
  let nodeStart = 0;
  for (const match of text.slice(0, firstArrow).matchAll(LEAD_BOUNDARY)) {
    nodeStart = (match.index ?? 0) + match[0].length;
  }

  // Last node ends at the first sentence terminator after the final arrow.
  ARROW.lastIndex = 0;
  let afterLastArrow = firstArrow;
  for (const match of text.matchAll(ARROW)) {
    afterLastArrow = (match.index ?? 0) + match[0].length;
  }
  const term = text.slice(afterLastArrow).match(/[.!?](\s|$)/);
  const nodeEnd = term ? afterLastArrow + (term.index ?? 0) : text.length;

  const nodes = text
    .slice(nodeStart, nodeEnd)
    .split(ARROW)
    .map((part) => part.trim())
    .filter(Boolean);
  if (nodes.length < 3) return null;

  return {
    lead: text.slice(0, nodeStart).trim(),
    nodes,
    trail: (term ? text.slice(afterLastArrow + (term.index ?? 0) + 1) : "").trim(),
  };
}

/** A flow node element (rendered as ChainNode → an <li>). */
function buildNode(value: string): Node {
  return {
    type: "paragraph",
    data: { hName: "chainnode" },
    children: [{ type: "text", value }],
  };
}

/** The flow wrapper (rendered as ChainFlow → an ordered list). */
function buildFlow(nodes: string[]): Node {
  return {
    type: "blockquote",
    data: { hName: "chainflow", hProperties: { count: String(nodes.length) } },
    children: nodes.map(buildNode),
  };
}

/** Remark transform: replace a chain-bearing paragraph with [lead-in prose?] [flow] [trailing prose?]. */
function remarkArrowFlow() {
  return (tree: Root): void => {
    const children = tree.children as unknown as Node[];
    const result: Node[] = [];

    for (const node of children) {
      if (node.type !== "paragraph" || node.data?.hName) {
        result.push(node);
        continue;
      }
      const flat = plainText(node.children ?? []);
      if (flat === null) {
        result.push(node);
        continue;
      }
      const chain = detectChain(flat);
      if (!chain) {
        result.push(node);
        continue;
      }

      if (chain.lead) result.push({ type: "paragraph", children: [{ type: "text", value: chain.lead }] });
      result.push(buildFlow(chain.nodes));
      if (chain.trail) result.push({ type: "paragraph", children: [{ type: "text", value: chain.trail }] });
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkArrowFlow };
