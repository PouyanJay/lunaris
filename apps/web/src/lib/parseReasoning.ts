/** A piece of a reasoning beat: ordinary prose, a JSON/code blob lifted out so the UI can render it
 *  as a *bounded* artifact, or a *group* of many small consecutive blobs collapsed into one (so a
 *  flood of tiny snippets — e.g. one prerequisite judgment per pair — can't stack into hundreds of
 *  cards). `closed` is false while a blob is still streaming in (an unterminated fence or unbalanced
 *  bracket), so the artifact can show a "streaming…" affordance and never grow unbounded. */
export type ReasoningSegment =
  | { kind: "prose"; text: string }
  | { kind: "json"; source: string; closed: boolean }
  | { kind: "jsonGroup"; sources: string[]; closed: boolean };

// A raw (unfenced) bracketed span is only lifted into an artifact when it's at least this long and
// looks like JSON — short inline `{x}` stays in the prose where it reads naturally.
const MIN_RAW_JSON = 40;
// Consecutive JSON blobs each shorter than this collapse into one group. Larger blobs (a curriculum
// dump, a visual spec) stay individual — they're worth their own artifact.
const SMALL_JSON = 200;
// Prose this short (after trimming) between two blobs is streaming noise (a stray ```json label, a
// fragment) — it doesn't break a run of grouped blobs.
const MAX_JOIN_PROSE = 20;
const FENCE = "```";

/**
 * Split a reasoning beat into prose and JSON/code segments. Fenced code blocks (```lang … ```),
 * balanced JSON objects/arrays, and a trailing still-streaming blob are each pulled out as `json`
 * segments; everything else stays `prose`. The concatenated `source`/`text` reproduces the input,
 * so nothing is dropped — it's only re-bucketed for bounded rendering.
 */
export function parseReasoning(text: string): ReasoningSegment[] {
  const segments: ReasoningSegment[] = [];
  let prose = "";
  let i = 0;

  const flushProse = () => {
    if (prose) {
      segments.push(...extractRawJson(prose));
      prose = "";
    }
  };

  while (i < text.length) {
    if (text.startsWith(FENCE, i)) {
      flushProse();
      const fence = readFence(text, i);
      segments.push({ kind: "json", source: fence.source, closed: fence.closed });
      i = fence.end;
    } else {
      prose += text[i];
      i += 1;
    }
  }
  flushProse();
  return coalesceSmallJson(mergeProse(segments));
}

/** Collapse runs of consecutive *small* JSON blobs (separated only by streaming noise) into one
 *  `jsonGroup`, so a flood of tiny snippets renders as a single bounded artifact rather than
 *  hundreds of cards. Large blobs and lone small blobs are left as individual `json` segments. */
function coalesceSmallJson(segments: ReasoningSegment[]): ReasoningSegment[] {
  const out: ReasoningSegment[] = [];
  let i = 0;
  while (i < segments.length) {
    const run = smallJsonRunAt(segments, i);
    if (run.sources.length >= 2) {
      out.push({ kind: "jsonGroup", sources: run.sources, closed: run.closed });
      i = run.next;
    } else {
      out.push(segments[i]!);
      i += 1;
    }
  }
  return out;
}

/** The run of small JSON blobs starting at `start` (skipping short noise prose between them): the
 *  collected sources, whether the last is closed, and the index just past the run. */
function smallJsonRunAt(
  segments: ReasoningSegment[],
  start: number,
): { sources: string[]; closed: boolean; next: number } {
  const sources: string[] = [];
  let closed = true;
  let i = start;
  while (i < segments.length) {
    const segment = segments[i]!;
    if (isSmallJson(segment)) {
      sources.push(segment.source);
      closed = segment.closed;
      i += 1;
      continue;
    }
    // A short noise-prose between two small blobs is skipped so the run continues across it.
    const next = segments[i + 1];
    if (
      sources.length > 0 &&
      segment.kind === "prose" &&
      segment.text.trim().length <= MAX_JOIN_PROSE &&
      next !== undefined &&
      isSmallJson(next)
    ) {
      i += 1;
      continue;
    }
    break;
  }
  return { sources, closed, next: i };
}

function isSmallJson(
  segment: ReasoningSegment,
): segment is { kind: "json"; source: string; closed: boolean } {
  return segment.kind === "json" && segment.source.length < SMALL_JSON;
}

/** Read a fenced block starting at `start` (a ``` run). Returns its inner source, whether the
 *  closing fence was seen, and the index just past the block (end of input if unterminated). */
function readFence(text: string, start: number): { source: string; closed: boolean; end: number } {
  // Skip the opening fence + optional language tag, up to (and including) the first newline.
  const firstNewline = text.indexOf("\n", start + FENCE.length);
  const bodyStart = firstNewline === -1 ? text.length : firstNewline + 1;
  const close = text.indexOf(FENCE, bodyStart);
  if (close === -1) {
    return { source: text.slice(bodyStart), closed: false, end: text.length };
  }
  return { source: text.slice(bodyStart, close), closed: true, end: close + FENCE.length };
}

/** Lift balanced JSON objects/arrays (and a trailing unbalanced one) out of a prose run. */
function extractRawJson(prose: string): ReasoningSegment[] {
  const segments: ReasoningSegment[] = [];
  let last = 0;
  let i = 0;

  while (i < prose.length) {
    const char = prose[i];
    if (char === "{" || char === "[") {
      const end = matchBalanced(prose, i);
      if (end === -1) {
        // Unbalanced from here to the end: a JSON blob still streaming in. Lift it (bounded) so it
        // can't run off the screen — but only if it's plausibly JSON, else leave it as prose.
        const tail = prose.slice(i);
        if (looksLikeJson(tail)) {
          pushProse(segments, prose.slice(last, i));
          segments.push({ kind: "json", source: tail, closed: false });
          return segments;
        }
        break;
      }
      const span = prose.slice(i, end);
      if (span.length >= MIN_RAW_JSON && looksLikeJson(span)) {
        pushProse(segments, prose.slice(last, i));
        segments.push({ kind: "json", source: span, closed: true });
        last = end;
      }
      i = end;
    } else {
      i += 1;
    }
  }
  pushProse(segments, prose.slice(last));
  return segments;
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

/** A bracketed span is "JSON-ish" if it carries a quote or a colon — enough to tell a data blob
 *  from incidental prose brackets like a `{n}` placeholder. */
function looksLikeJson(span: string): boolean {
  return span.includes('"') || span.includes(":");
}

function pushProse(segments: ReasoningSegment[], text: string): void {
  if (text) segments.push({ kind: "prose", text });
}

/** Coalesce adjacent prose segments (split apart by skipped short brackets) back into one. */
function mergeProse(segments: ReasoningSegment[]): ReasoningSegment[] {
  const merged: ReasoningSegment[] = [];
  for (const segment of segments) {
    const previous = merged[merged.length - 1];
    if (segment.kind === "prose" && previous?.kind === "prose") {
      merged[merged.length - 1] = { kind: "prose", text: previous.text + segment.text };
    } else {
      merged.push(segment);
    }
  }
  return merged;
}
