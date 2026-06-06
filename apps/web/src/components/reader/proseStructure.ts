import type { Root } from "mdast";
import { SKIP, visit } from "unist-util-visit";

/** Authored lesson prose often carries structure as plain sentence text — inline enumerations like
 *  "(1) … (2) … (3) …" or "(a) … (b) … (c) …", and labelled sections like "Move 1: …", "Step 2: …".
 *  This remark transform lifts those patterns into real, interactive Markup so the reader can format
 *  them: enumerations become ordered lists, and a run of labelled sections becomes collapsible
 *  `<details>` panels (open by default) headed by their label. It is deliberately conservative — it
 *  fires only on unambiguous patterns (a sequence starting at 1/"a"; ≥2 sibling labelled sections) so
 *  ordinary prose, citations, and stray parentheses are left untouched. */

/** Loosely-typed mdast node — we build a handful of nodes and read text off existing ones; the strict
 *  mdast unions add friction here without catching real bugs, so we keep one permissive shape. */
interface Node {
  type: string;
  value?: string;
  children?: Node[];
  ordered?: boolean;
  spread?: boolean;
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

const SECTION_LABEL = /^((?:Move|Step|Part|Phase|Stage|Principle|Strategy|Rule)\s+\d+)\s*:\s+/i;
/** Captures the label + title sentence (up to the first period) and the rest of the paragraph. */
const SECTION_SPLIT =
  /^((?:Move|Step|Part|Phase|Stage|Principle|Strategy|Rule)\s+\d+\s*:\s*[^.]*)\.?\s*([\s\S]*)$/i;

type EnumKind = "decimal" | "lower-alpha";

/** The literal marker token that opens item `index` (0-based): (1)/(2)… or (a)/(b)…. */
function markerFor(kind: EnumKind, index: number): string {
  return kind === "decimal" ? `(${index + 1})` : `(${String.fromCharCode(97 + index)})`;
}

/** The flattened text of a run of phrasing nodes. */
function textOf(nodes: Node[]): string {
  return nodes
    .map((node) => (node.type === "text" ? (node.value ?? "") : textOf(node.children ?? [])))
    .join("");
}

/** Detect a sequential parenthesised enumeration that starts at the first marker — numeric "(1)…(2)"
 *  or alphabetical "(a)…(b)" — looking for the exact expected tokens so unrelated parentheses (e.g.
 *  "(word choice, voice)") never trigger it. */
function detectEnumeration(text: string): EnumKind | null {
  const oneAt = text.indexOf("(1)");
  if (oneAt !== -1 && text.indexOf("(2)") > oneAt) return "decimal";
  const aAt = text.indexOf("(a)");
  if (aAt !== -1 && text.indexOf("(b)") > aAt) return "lower-alpha";
  return null;
}

/** Trim leading whitespace and trailing list separators ("; ", spaces) off a list item's edges,
 *  preserving inline formatting nodes in between. */
function trimItem(nodes: Node[]): Node[] {
  const out = nodes.map((node) => ({ ...node }));
  const first = out[0];
  if (first?.type === "text") first.value = (first.value ?? "").replace(/^\s+/, "");
  const last = out[out.length - 1];
  if (last?.type === "text") last.value = (last.value ?? "").replace(/[\s;]+$/, "");
  return out.filter((node) => !(node.type === "text" && node.value === ""));
}

/** Walk a paragraph's inline children, splitting at each expected marker into the lead-in (text before
 *  the first marker) and one segment per item — inline formatting (strong/em/links) rides along. */
function splitEnumeration(children: Node[], kind: EnumKind): { lead: Node[]; items: Node[][] } {
  const segments: Node[][] = [[]];
  let lookingFor = 0;
  let current = segments[0]!;

  for (const child of children) {
    if (child.type !== "text") {
      current.push(child);
      continue;
    }
    let value = child.value ?? "";
    for (;;) {
      const token = markerFor(kind, lookingFor);
      const at = value.indexOf(token);
      if (at === -1) break;
      const before = value.slice(0, at);
      if (before) current.push({ type: "text", value: before });
      const next: Node[] = [];
      segments.push(next);
      current = next;
      value = value.slice(at + token.length);
      lookingFor += 1;
    }
    if (value) current.push({ type: "text", value });
  }

  return { lead: segments[0]!, items: segments.slice(1) };
}

/** Build an ordered list (numeric or alpha-typed) from item segments. */
function buildList(items: Node[][], kind: EnumKind): Node {
  const list: Node = {
    type: "list",
    ordered: true,
    spread: false,
    children: items.map((segment) => ({
      type: "listItem",
      spread: false,
      children: [{ type: "paragraph", children: trimItem(segment) }],
    })),
  };
  if (kind === "lower-alpha") list.data = { hProperties: { type: "a" } };
  return list;
}

/** Pass 1 — group consecutive labelled paragraphs ("Move 1: …", "Move 2: …") into collapsible
 *  sections. Each section absorbs the following non-labelled blocks as its body, so multi-paragraph
 *  sections stay whole. Only fires when there are ≥2 labelled siblings (a real section structure). */
function groupSections(root: Root): void {
  const children = root.children as unknown as Node[];
  const isLabel = (node: Node): boolean =>
    node.type === "paragraph" &&
    node.children?.[0]?.type === "text" &&
    SECTION_LABEL.test(node.children[0].value ?? "");

  if (children.filter(isLabel).length < 2) return;

  const result: Node[] = [];
  let i = 0;
  while (i < children.length) {
    const head = children[i]!;
    if (!isLabel(head)) {
      result.push(head);
      i += 1;
      continue;
    }
    let j = i + 1;
    while (j < children.length && !isLabel(children[j]!)) j += 1;
    result.push(buildSection(head, children.slice(i + 1, j)));
    i = j;
  }
  root.children = result as unknown as Root["children"];
}

/** Turn a labelled paragraph + its following body blocks into a `<details open>` whose `<summary>` is
 *  the label and title, and whose body is the remainder of the paragraph plus the trailing blocks. */
function buildSection(head: Node, rest: Node[]): Node {
  const firstText = head.children?.[0];
  const raw = firstText?.type === "text" ? (firstText.value ?? "") : "";
  const match = raw.match(SECTION_SPLIT);
  const summaryText = (match ? match[1]! : raw).replace(/\s+$/, "");
  const remainder = match ? match[2]! : "";

  const summary: Node = {
    type: "paragraph",
    data: { hName: "summary" },
    children: [{ type: "text", value: summaryText }],
  };

  const firstBody: Node[] = [];
  if (remainder) firstBody.push({ type: "text", value: remainder });
  firstBody.push(...(head.children ?? []).slice(1));

  const body: Node[] = [];
  if (textOf(firstBody).trim()) body.push({ type: "paragraph", children: firstBody });
  body.push(...rest);

  return {
    type: "blockquote", // a known handler whose tag we override to <details> via hName
    data: { hName: "details", hProperties: { open: true } },
    children: [summary, ...body],
  };
}

/** Remark transform: structure labelled sections, then split inline enumerations everywhere (so
 *  enumerations inside a section's body still become lists). */
function remarkProseStructure() {
  return (tree: Root): void => {
    groupSections(tree);

    visit(tree, "paragraph", (node, index, parent) => {
      if (index === undefined || !parent) return;
      // Don't restructure a generated <summary> paragraph.
      const data = (node as unknown as Node).data;
      if (data?.hName === "summary") return;

      const children = (node as unknown as Node).children ?? [];
      const kind = detectEnumeration(textOf(children));
      if (!kind) return;

      const { lead, items } = splitEnumeration(children, kind);
      if (items.length < 2) return;

      const replacement: Node[] = [];
      const leadTrimmed = lead.map((child) => ({ ...child }));
      const leadLast = leadTrimmed[leadTrimmed.length - 1];
      if (leadLast?.type === "text") leadLast.value = (leadLast.value ?? "").replace(/\s+$/, "");
      if (textOf(leadTrimmed).trim())
        replacement.push({ type: "paragraph", children: leadTrimmed });
      replacement.push(buildList(items, kind));

      const siblings = (parent as unknown as Node).children!;
      siblings.splice(index, 1, ...replacement);
      return [SKIP, index + replacement.length];
    });
  };
}

export { remarkProseStructure };
