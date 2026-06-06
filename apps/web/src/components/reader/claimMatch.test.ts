import { describe, expect, it } from "vitest";

import { matchClaimToSentence, splitSentences } from "./claimMatch";

describe("splitSentences", () => {
  it("splits prose into sentences and preserves the original text", () => {
    const prose =
      "Binary search halves the range. It compares the midpoint each step! Does it terminate?";

    const sentences = splitSentences(prose);

    expect(sentences).toHaveLength(3);
    expect(sentences[0]).toBe("Binary search halves the range.");
    expect(sentences[1]).toBe("It compares the midpoint each step!");
    expect(sentences[2]).toBe("Does it terminate?");
  });

  it("does not split on common abbreviations or decimals", () => {
    const prose = "The result is 3.14 for e.g. a circle. That holds.";

    const sentences = splitSentences(prose);

    expect(sentences).toHaveLength(2);
    expect(sentences[0]).toContain("3.14");
    expect(sentences[0]).toContain("e.g.");
  });

  it("returns an empty array for blank prose", () => {
    expect(splitSentences("   ")).toEqual([]);
  });
});

describe("matchClaimToSentence", () => {
  it("finds the sentence that best covers the claim's significant words", () => {
    const claim =
      "Logical relationships are clearer through deliberate clause structures than juxtaposition.";
    const prose =
      "You will practice on a weak text. Subordinate clauses explicitly name the logical " +
      "relationship between ideas, so deliberate clause structures make logical relationships " +
      "clearer than plain juxtaposition. Then revise your own paragraph.";

    const match = matchClaimToSentence(claim, prose);

    expect(match).not.toBeNull();
    expect(match?.index).toBe(1);
    expect(match?.sentence).toContain("deliberate clause structures");
  });

  it("returns null when no sentence shares enough significant words (fallback to phase)", () => {
    const claim =
      "Casual communication relies on general terms rather than precise discipline-specific language.";
    const prose = "Trace binary search on a sorted array. Where else does halving a range help?";

    expect(matchClaimToSentence(claim, prose)).toBeNull();
  });

  it("ignores stopwords so a sentence of only filler words never matches", () => {
    const claim = "Specialized vocabulary has narrower precise meanings used by domain experts.";
    const prose = "And so it was that they went on with it. But then there it is.";

    expect(matchClaimToSentence(claim, prose)).toBeNull();
  });

  it("is case and punctuation insensitive", () => {
    const claim = "DISCOURSE markers, signal logical relationships!";
    const prose = "Discourse markers signal logical relationships in professional writing.";

    const match = matchClaimToSentence(claim, prose);

    expect(match?.index).toBe(0);
  });

  it("returns null for empty prose or empty claim", () => {
    expect(matchClaimToSentence("a claim", "")).toBeNull();
    expect(matchClaimToSentence("", "Some prose here about things.")).toBeNull();
  });
});
