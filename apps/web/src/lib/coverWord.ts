const STOPWORDS: ReadonlySet<string> = new Set([
  "the",
  "and",
  "for",
  "with",
  "how",
  "why",
  "what",
  "your",
  "from",
  "into",
  "that",
  "this",
  "a",
  "an",
  "of",
  "to",
  "in",
  "on",
]);

/** The word to ghost across the Typographic cover: the longest content word in the topic (stopwords
 *  skipped), falling back to the first word, then the whole (trimmed) topic — so an all-stopword or
 *  empty topic still renders something rather than a blank cover. Uppercased by the cover's CSS. */
export function coverWord(topic: string): string {
  const trimmed = topic.trim();
  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length === 0) return trimmed;
  const content = words.filter((w) => !STOPWORDS.has(w.toLowerCase()) && w.length >= 3);
  const pool = content.length > 0 ? content : words;
  return pool.reduce((longest, w) => (w.length > longest.length ? w : longest), pool[0] ?? trimmed);
}
