import type { Root } from "mdast";

/** Authored lesson prose often opens a passage with an ALL-CAPS (or Title-Case) label — "STRATEGY:",
 *  "UPSTREAM LAYER (alarmins):", "CANONICAL CYTOKINES:" — then runs the section as flat text. This
 *  remark transform lifts that lead-in into an eyebrow section head (`seclabel`), splitting the label
 *  off from its body so a wall of labelled prose reads as scannable sections. It is presentation-only:
 *  the label words are preserved verbatim (only the trailing colon, pure punctuation, is dropped) and
 *  the body text is never altered. Conservative: it fires only on a genuine leading label — 1–4 words
 *  of ≥2 chars each — so ordinary capitalised sentences ("The T2 axis…") are left untouched. */

/** Loosely-typed mdast node — we build a couple of nodes and read text off existing ones. */
interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

/** A single label word: ≥2 chars, ALL-CAPS with optional inner digits ("IL"→no, "TSLP"→yes). */
const WORD = "[A-Z][A-Z0-9]+";
/** Leading section label: 1–4 uppercase words (space/slash/hyphen joined), optional "(qualifier)",
 *  then a colon and at least one space. `s` flag lets the body ($3) span newlines. */
const LEADING_LABEL = new RegExp(
  `^(${WORD}(?:[ /-]${WORD}){0,3})\\s*(?:\\(([^)]+)\\))?\\s*:\\s+([\\s\\S]+)$`,
);

/** The eyebrow section-label element (rendered as SectionLabel). Its text rides as attributes,
 *  vetted by the sanitiser's allow-list. */
function buildLabel(heading: string, qual: string): Node {
  return {
    type: "paragraph",
    data: { hName: "seclabel", hProperties: { heading, qual } },
    children: [],
  };
}

/** Remark transform: split any paragraph that opens with a section label into an eyebrow head plus a
 *  body paragraph (the remainder of the first text node, followed by the paragraph's other children). */
function remarkSectionLabels() {
  return (tree: Root): void => {
    const children = tree.children as unknown as Node[];
    const result: Node[] = [];

    for (const node of children) {
      if (node.type !== "paragraph" || node.data?.hName) {
        result.push(node);
        continue;
      }
      const first = node.children?.[0];
      if (!first || first.type !== "text") {
        result.push(node);
        continue;
      }
      const match = (first.value ?? "").match(LEADING_LABEL);
      if (!match) {
        result.push(node);
        continue;
      }

      const heading = match[1]!.trim();
      const qual = (match[2] ?? "").trim();
      const rest = match[3] ?? "";

      result.push(buildLabel(heading, qual));

      const body: Node[] = [];
      if (rest) body.push({ type: "text", value: rest });
      body.push(...(node.children ?? []).slice(1));
      if (body.length) result.push({ type: "paragraph", children: body });
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkSectionLabels };
