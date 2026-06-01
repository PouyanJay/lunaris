/** A piece of a reasoning beat: ordinary prose, a JSON/code blob lifted out so the UI can render it
 *  as a *bounded* artifact, or a *group* of many small consecutive blobs collapsed into one (so a
 *  flood of tiny snippets — e.g. one prerequisite judgment per pair — can't stack into hundreds of
 *  cards). `closed` is false while a blob is still streaming in (its JSON hasn't closed yet), so the
 *  artifact can show a "streaming…" affordance and never grow unbounded. */
export type ReasoningSegment =
  | { kind: "prose"; text: string }
  | { kind: "json"; source: string; closed: boolean }
  | { kind: "jsonGroup"; sources: string[]; closed: boolean };

// A line needs at least this many JSON-punctuation chars before the density check fires, so a lone
// stray colon (e.g. "Result: done") can't trip the heuristic alone.
const MIN_JSON_PUNCT = 2;
// A non-empty line whose characters are at least this fraction JSON punctuation counts as JSON
// content. Calibrated against the prereq-judgment flood (objects run ~35-40% punctuation) while
// ordinary prose (an occasional colon or quote) stays well below.
const JSON_PUNCT_DENSITY = 0.2;

/**
 * Split a reasoning beat into prose and JSON segments. The model interleaves real sentences with a
 * flood of JSON (often malformed mid-stream: stray ```json labels, partial objects, fragments), so
 * this works LINE BY LINE rather than parsing the stream char-by-char: a region *opens* on a clear
 * JSON line (a fence, a bare label, or an object/array opener) and *continues* across value, closer,
 * fragment, and blank lines; the clean balanced objects are then extracted from the region (the
 * labels and fragments around them are ignored). A region with one object renders as a single
 * artifact (a diagram / a bounded tree), many become one collapsed group, and real prose stays
 * prose — so a flood collapses to ONE artifact no matter how ragged the underlying text.
 *
 * Tradeoff: prose and JSON are assumed to live on separate lines (as the model emits them). A line
 * mixing both classifies as JSON, and any prose before its first bracket is dropped.
 */
export function parseReasoning(text: string): ReasoningSegment[] {
  const lines = text.split("\n");
  const segments: ReasoningSegment[] = [];
  let i = 0;

  while (i < lines.length) {
    if (opensJsonRegion(lines[i]!)) {
      const start = i;
      i += 1;
      while (i < lines.length && continuesJsonRegion(lines[i]!)) i += 1;
      segments.push(...regionToSegments(lines.slice(start, i).join("\n")));
    } else {
      const start = i;
      i += 1;
      while (i < lines.length && !opensJsonRegion(lines[i]!)) i += 1;
      const prose = lines.slice(start, i).join("\n").trim();
      if (prose) segments.push({ kind: "prose", text: prose });
    }
  }
  return segments;
}

/** A line that clearly OPENS a JSON region: a code fence, a bare ```json`` label, or an object/array
 *  opener. Deliberately strict — a line merely *starting* with a quote (a quoted sentence) must not
 *  begin a region, only continue one. */
function opensJsonRegion(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("```") || trimmed === "json" || /^[{[]/.test(trimmed);
}

/** A line that CONTINUES an open JSON region: an opener, a value / closer / fragment line (starts or
 *  ends with JSON structure), a blank line, or one that's predominantly JSON punctuation. Looser than
 *  {@link opensJsonRegion} so a multi-line object's value and closing-brace lines stay in the region. */
function continuesJsonRegion(line: string): boolean {
  const trimmed = line.trim();
  if (trimmed === "") return true;
  if (opensJsonRegion(trimmed)) return true;
  if (/^["}\]]/.test(trimmed) || /[}\],]$/.test(trimmed)) return true;
  const punct = (trimmed.match(/[{}[\]":,]/g) ?? []).length;
  return punct >= MIN_JSON_PUNCT && punct / trimmed.length >= JSON_PUNCT_DENSITY;
}

/** Turn one JSON region into segments: extract the clean balanced objects (ignoring the fence
 *  labels and fragments around them). One object → a single artifact; many → a collapsed group; a
 *  region with only a still-opening object → one bounded, streaming artifact. */
function regionToSegments(region: string): ReasoningSegment[] {
  const { values, openTail } = extractJsonValues(region);
  if (values.length === 0) {
    // Only a genuinely opening object/array is worth a (streaming) artifact; a region of pure label
    // or fragment noise (no bracket) is dropped rather than shown as an empty card.
    return openTail ? [{ kind: "json", source: openTail, closed: false }] : [];
  }
  if (values.length === 1 && openTail === null) {
    return [{ kind: "json", source: values[0]!, closed: true }];
  }
  const sources = openTail ? [...values, openTail] : values;
  return [{ kind: "jsonGroup", sources, closed: openTail === null }];
}

/** Pull every balanced JSON object/array out of a region, plus a trailing still-opening one (if the
 *  region ends mid-object — a streaming blob). Non-bracket noise between values is skipped. */
function extractJsonValues(region: string): { values: string[]; openTail: string | null } {
  const values: string[] = [];
  let i = 0;
  while (i < region.length) {
    const char = region[i];
    if (char === "{" || char === "[") {
      const end = matchBalanced(region, i);
      if (end === -1) return { values, openTail: region.slice(i).trim() };
      values.push(region.slice(i, end));
      i = end;
    } else {
      i += 1;
    }
  }
  return { values, openTail: null };
}

/** Index just past the bracket matching the opener at `start`, or -1 if it never closes. String
 *  literals (and their escapes) are skipped so braces inside strings don't miscount the depth. */
function matchBalanced(text: string, start: number): number {
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i += 1) {
    const char = text[i];
    if (inString) {
      if (char === "\\") i += 1;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') inString = true;
    else if (char === "{" || char === "[") depth += 1;
    else if (char === "}" || char === "]") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}
