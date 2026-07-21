import type { Root } from "mdast";

/** A single over-long paragraph reads as a wall. This remark transform breaks a plain-text paragraph
 *  that exceeds a word budget into smaller paragraphs AT SENTENCE BOUNDARIES only — never mid-sentence
 *  — so the reader gets air without any wording change (it only inserts paragraph breaks). Runs after
 *  the structural lifts (R1/R3/R4), so it only re-rhythms the prose those leave behind. Conservative:
 *  short paragraphs and single long sentences are left whole. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string };
}

/** Below this many words a paragraph is never split. */
const THRESHOLD = 55;
/** Greedy target words per resulting paragraph. */
const TARGET = 45;
/** A trailing group smaller than this is merged back so we never orphan a stray clause. */
const MIN_TAIL = 12;

/** The flat string of a paragraph iff every child is a plain text node. */
function plainText(children: Node[]): string | null {
  let out = "";
  for (const child of children) {
    if (child.type !== "text") return null;
    out += child.value ?? "";
  }
  return out;
}

function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/** Split text at "… . Next" boundaries (terminator + space + capital/digit/quote). */
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=["'“(]?[A-Z0-9])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

/** Group sentences greedily into paragraphs of ~TARGET words, or null when nothing should split. */
function regroup(text: string): string[] | null {
  if (wordCount(text) <= THRESHOLD) return null;
  const sentences = splitSentences(text);
  if (sentences.length < 2) return null;

  const groups: string[] = [];
  let current: string[] = [];
  let words = 0;
  for (const sentence of sentences) {
    current.push(sentence);
    words += wordCount(sentence);
    if (words >= TARGET) {
      groups.push(current.join(" "));
      current = [];
      words = 0;
    }
  }
  if (current.length) {
    if (groups.length && words < MIN_TAIL) {
      groups[groups.length - 1] += ` ${current.join(" ")}`;
    } else {
      groups.push(current.join(" "));
    }
  }

  return groups.length >= 2 ? groups : null;
}

function remarkParagraphRhythm() {
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
      const groups = regroup(flat);
      if (!groups) {
        result.push(node);
        continue;
      }
      for (const group of groups) {
        result.push({ type: "paragraph", children: [{ type: "text", value: group }] });
      }
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkParagraphRhythm };
