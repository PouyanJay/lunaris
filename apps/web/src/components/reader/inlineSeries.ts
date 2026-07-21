import type { Root } from "mdast";

import { plainText, splitAtSentenceBoundaries } from "./proseText";
import { STOP_TOKENS, TOKEN_ID } from "./tokenShapes";

/** Authored prose often hides a list inside a sentence — "three core cytokines—IL-4, IL-5, and
 *  IL-13", or a run of parallel "IL-4 drives…", "IL-5 recruits…" sentences. This remark transform
 *  lifts the two shapes:
 *   - R4a: a "cue: a, b, and c" (or "cue—a, b, and c") run → a bullet list, with the lead-in and any
 *     trailing sentence kept as prose;
 *   - R4b: ≥2 consecutive sentences each led by a data token → a keyed definition list.
 *  Presentation-only: item words are preserved verbatim. Conservative: R4a needs a terminal and/or
 *  connector and short (≤6-word) items, so dash-appositives and long prose clauses stay inline; R4b
 *  needs every sentence in the paragraph to be token-led. */

interface Node {
  type: string;
  value?: string;
  children?: Node[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

// ─── R4b: keyed list (token-led sentences) ──────────────────────────────────────────────────────

/** A sentence keyed by a data token then a lowercase predicate ("IL-5 recruits …"). */
const KEYED_SENTENCE = new RegExp(`^(${TOKEN_ID})\\s+([a-z][\\s\\S]*)$`);

interface KeyedRow {
  term: string;
  def: string;
}

/** Parse a paragraph into keyed rows, or null unless it is ≥2 sentences that are ALL keyed by a real
 *  token — an all-caps emphasis word (NEVER/ALWAYS/ONLY) is rejected so imperative prose isn't lifted. */
function detectKeyedList(text: string): KeyedRow[] | null {
  const sentences = splitAtSentenceBoundaries(text);
  if (sentences.length < 2) return null;

  const rows: KeyedRow[] = [];
  for (const sentence of sentences) {
    const match = sentence.match(KEYED_SENTENCE);
    if (!match || STOP_TOKENS.has(match[1]!.toUpperCase())) return null;
    rows.push({ term: match[1]!.trim(), def: match[2]!.trim() });
  }
  return rows;
}

function buildKeyedList(rows: KeyedRow[]): Node {
  return {
    type: "blockquote",
    data: { hName: "keyedlist" },
    children: rows.map((row) => ({
      type: "paragraph",
      data: { hName: "keyedrow", hProperties: { term: row.term } },
      children: [{ type: "text", value: row.def }],
    })),
  };
}

// ─── R4a: bullet series (cue + comma run) ───────────────────────────────────────────────────────

interface Series {
  lead: string;
  items: string[];
  trail: string;
}

/** Split a candidate span ("a, b, and c") into ≥3 short items, or null when it isn't a real series
 *  (no comma, no terminal and/or connector, or an item that is really a prose clause). */
function extractItems(span: string): string[] | null {
  if (!span.includes(",")) return null;
  const parts = span
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 2) return null;

  const last = parts.pop()!;
  const connector = last.match(/^(?:(.+?)\s+)?(?:and|or)\s+(.+)$/i);
  if (!connector) return null;

  const items = [...parts];
  if (connector[1]) items.push(connector[1].trim());
  items.push(connector[2]!.trim());
  if (items.length < 3) return null;

  for (const item of items) {
    if (!item || item.split(/\s+/).length > 6) return null;
  }
  return items;
}

/** Find the first cue (":", em/en dash) whose following span is a real series, splitting the text
 *  into lead-in prose, the items, and the trailing sentence. */
function detectSeries(text: string): Series | null {
  for (const cue of text.matchAll(/[:—–]/g)) {
    const cueAt = cue.index ?? 0;
    const afterCue = text.slice(cueAt + 1).replace(/^\s+/, "");
    const spanStart = text.length - afterCue.length;
    const term = afterCue.search(/[.!?](\s|$)/);
    const span = term === -1 ? afterCue : afterCue.slice(0, term);

    const items = extractItems(span);
    if (!items) continue;

    return {
      lead: text.slice(0, cueAt).trim(),
      items,
      trail: term === -1 ? "" : text.slice(spanStart + term + 1).trim(),
    };
  }
  return null;
}

function buildBulletList(items: string[]): Node {
  return {
    type: "list",
    ordered: false,
    spread: false,
    children: items.map((item) => ({
      type: "listItem",
      spread: false,
      children: [{ type: "paragraph", children: [{ type: "text", value: item }] }],
    })),
  } as Node;
}

// ─── transform ──────────────────────────────────────────────────────────────────────────────────

function remarkInlineSeries() {
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

      const keyed = detectKeyedList(flat);
      if (keyed) {
        result.push(buildKeyedList(keyed));
        continue;
      }

      const series = detectSeries(flat);
      if (!series) {
        result.push(node);
        continue;
      }
      if (series.lead) result.push({ type: "paragraph", children: [{ type: "text", value: series.lead }] });
      result.push(buildBulletList(series.items));
      if (series.trail) result.push({ type: "paragraph", children: [{ type: "text", value: series.trail }] });
    }

    tree.children = result as unknown as Root["children"];
  };
}

export { remarkInlineSeries };
