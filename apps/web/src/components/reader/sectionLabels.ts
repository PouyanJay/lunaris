import type { Root } from "mdast";

/** Authored lesson prose often runs a whole passage as one flowing paragraph, marking its structure
 *  only with ALL-CAPS lead-in labels — "STRATEGY:", "UPSTREAM LAYER (alarmins):", "CANONICAL
 *  CYTOKINES:" — that recur mid-paragraph after each sentence. This remark transform lifts every such
 *  label into an eyebrow section head (`seclabel`) and splits the body around it, so a wall of
 *  labelled prose reads as scannable sections. It is presentation-only: label words are preserved
 *  verbatim (only the trailing colon, pure punctuation, is dropped) and body text is never altered.
 *  Conservative: a label is 1–4 ALL-CAPS words (≥2 chars each) sitting at the paragraph start or right
 *  after a sentence end, so ordinary capitalised sentences ("The T2 axis…") are left untouched; the
 *  callout lead-ins (Note/Tip/…) are deferred to `remarkRichDirectives`. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

/** A single label word: ≥2 chars, ALL-CAPS with optional inner digits ("TSLP", "IL"→word, not "A"). */
const WORD = "[A-Z][A-Z0-9]+";
/** A label at a segment boundary: paragraph start OR after sentence-ending punctuation (+ optional
 *  closing quote/bracket) and whitespace. Group 1 = the boundary (stays with the previous body),
 *  group 2 = the label words, group 3 = an optional "(qualifier)". */
const LABEL_AT_BOUNDARY = new RegExp(
  `(^|[.!?][")'\\u201d\\u2019]?\\s+)(${WORD}(?:[ /-]${WORD}){0,3})(?:\\s*\\(([^)]+)\\))?:\\s+`,
  "g",
);

/** Callout lead-in words owned by `remarkRichDirectives` — never claimed as section labels, so the
 *  existing "Note:/Tip:/…" callout lift keeps working (and its lowercase forms too). */
const CALLOUT_WORDS = new Set(["NOTE", "TIP", "INSIGHT", "WARNING", "EXAMPLE", "KEY TAKEAWAY"]);

interface Section {
  heading?: string;
  qual?: string;
  text: string;
}

/** The flat string of a paragraph iff every child is a plain text node (the common authored case);
 *  null when inline formatting (em/strong/links) is present, so we fall back to leaving it be. */
function plainText(children: Node[]): string | null {
  let out = "";
  for (const child of children) {
    if (child.type !== "text") return null;
    out += child.value ?? "";
  }
  return out;
}

/** Split a paragraph's flat text into a lead-in (index 0, no heading) plus one section per label. */
function splitByLabels(value: string): Section[] {
  const sections: Section[] = [{ text: "" }];
  let current = sections[0]!;
  let lastEnd = 0;

  for (const match of value.matchAll(LABEL_AT_BOUNDARY)) {
    const boundary = match[1] ?? "";
    const heading = match[2]!.trim();
    const start = match.index ?? 0;

    // Defer callout lead-ins: leave the matched text in the current section untouched.
    if (CALLOUT_WORDS.has(heading.toUpperCase())) continue;

    current.text += value.slice(lastEnd, start + boundary.length);
    current = { heading, qual: (match[3] ?? "").trim(), text: "" };
    sections.push(current);
    lastEnd = start + match[0].length;
  }
  current.text += value.slice(lastEnd);
  return sections;
}

/** The eyebrow section-label element (rendered as SectionLabel). Text rides as sanitised attributes. */
function buildLabel(heading: string, qual: string): Node {
  return {
    type: "paragraph",
    data: { hName: "seclabel", hProperties: { heading, qual } },
    children: [],
  };
}

/** Remark transform: replace each label-bearing paragraph with an eyebrow head + body paragraph per
 *  section (and a lead-in paragraph for any text before the first label). */
function remarkSectionLabels() {
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
      const sections = splitByLabels(flat);
      if (sections.length < 2) {
        result.push(node);
        continue;
      }

      for (const section of sections) {
        if (section.heading) result.push(buildLabel(section.heading, section.qual ?? ""));
        const body = section.text.trim();
        if (body) result.push({ type: "paragraph", children: [{ type: "text", value: body }] });
      }
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkSectionLabels };
