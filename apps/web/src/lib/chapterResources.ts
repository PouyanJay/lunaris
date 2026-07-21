import type { Resource } from "../types/course";
import type { VideoChapter } from "./videoJobs";

/** One resource docked under a chapter, with its relevance to that chapter. */
export interface ScoredResource {
  resource: Resource;
  /** 0–100: the share of the chapter's key terms this resource's title/why covers. */
  rel: number;
}

export interface ChapterResourceMatch {
  /** Resources docked under each chapter id, most-relevant first. */
  byChapter: Map<string, ScoredResource[]>;
  /** Resources that matched no chapter — for a lesson-level fallback dock. */
  unmatched: Resource[];
}

/** Function words + connectives that carry no topical signal — dropped before matching. */
const STOPWORDS = new Set([
  "the",
  "a",
  "an",
  "and",
  "or",
  "of",
  "to",
  "in",
  "on",
  "for",
  "with",
  "is",
  "are",
  "was",
  "were",
  "be",
  "by",
  "it",
  "its",
  "this",
  "that",
  "these",
  "those",
  "as",
  "at",
  "from",
  "how",
  "why",
  "what",
  "when",
  "into",
  "your",
  "you",
  "we",
  "our",
  "their",
  "they",
  "not",
  "but",
  "so",
  "if",
  "then",
  "than",
  "about",
  "over",
  "under",
  "via",
  "per",
]);

/** Lowercase, split on non-alphanumerics, drop stopwords + tokens under 3 chars → a token set. */
function tokenize(text: string): Set<string> {
  const tokens = new Set<string>();
  for (const raw of text.toLowerCase().split(/[^a-z0-9]+/)) {
    if (raw.length >= 3 && !STOPWORDS.has(raw)) tokens.add(raw);
  }
  return tokens;
}

/** A chapter's distinct topical terms: its title words plus its key-term words (phrases flattened
 *  to tokens), so "koch curve" contributes both "koch" and "curve". */
function chapterTerms(chapter: VideoChapter): Set<string> {
  const terms = tokenize(chapter.title);
  for (const keyTerm of chapter.keyTerms ?? []) {
    for (const token of tokenize(keyTerm)) terms.add(token);
  }
  return terms;
}

/** Match each lesson resource to the chapter whose key terms it best covers — a deterministic,
 *  keyless overlap: `rel` is the share of a chapter's terms the resource's title/why contains, and
 *  each resource is docked under its single best chapter (ties → the earlier chapter). Resources
 *  that share no term with any chapter come back `unmatched` for a lesson-level fallback dock. */
export function matchResourcesToChapters(
  chapters: VideoChapter[],
  resources: Resource[],
): ChapterResourceMatch {
  const scored = chapters.map((chapter) => ({ id: chapter.id, terms: chapterTerms(chapter) }));
  const byChapter = new Map<string, ScoredResource[]>();
  const unmatched: Resource[] = [];

  for (const resource of resources) {
    const text = tokenize(`${resource.title} ${resource.why}`);
    let best: { id: string; rel: number } | null = null;
    for (const { id, terms } of scored) {
      if (terms.size === 0) continue;
      let matched = 0;
      for (const term of terms) if (text.has(term)) matched += 1;
      if (matched === 0) continue;
      const rel = matched / terms.size;
      // Strict `>` keeps the earliest chapter on a tie.
      if (!best || rel > best.rel) best = { id, rel };
    }
    if (best) {
      const list = byChapter.get(best.id) ?? [];
      list.push({ resource, rel: Math.round(best.rel * 100) });
      byChapter.set(best.id, list);
    } else {
      unmatched.push(resource);
    }
  }

  for (const list of byChapter.values()) list.sort((a, b) => b.rel - a.rel);
  return { byChapter, unmatched };
}
