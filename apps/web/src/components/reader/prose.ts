import { splitSentences } from "./claimMatch";

/** Group a phase's prose into readable paragraphs (as lists of sentence indices into
 *  `splitSentences(prose)`), so the reading column gets visual rhythm instead of one wall of text.
 *
 *  The authored prose arrives as a single unbroken string, so paragraph breaks are inferred: start a
 *  fresh paragraph when a sentence opens with a structural cue ("Move 1:", "Step 2", "Example",
 *  "For example", "Notice", "First/Second/…", "Finally"), and otherwise every few sentences so a
 *  long run still breathes. Returning indices (not text) lets the renderer wrap a specific
 *  claim-matched sentence in place without re-splitting differently. */
const MAX_SENTENCES_PER_PARAGRAPH = 3;
const CUE = /^(move\s+\d|step\s+\d|example|for example|notice|first|second|third|finally|next)\b/i;

export function paragraphize(prose: string): number[][] {
  const sentences = splitSentences(prose);
  const paragraphs: number[][] = [];
  let current: number[] = [];
  sentences.forEach((sentence, index) => {
    const startsNewSection = current.length > 0 && CUE.test(sentence);
    const isFull = current.length >= MAX_SENTENCES_PER_PARAGRAPH;
    if (startsNewSection || isFull) {
      paragraphs.push(current);
      current = [];
    }
    current.push(index);
  });
  if (current.length > 0) paragraphs.push(current);
  return paragraphs;
}
