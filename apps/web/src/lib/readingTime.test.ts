import { describe, expect, it } from "vitest";

import { makeLesson } from "../test/fixtures";
import { estimateReadingMinutes } from "./readingTime";

describe("estimateReadingMinutes", () => {
  it("rounds a short lesson up to one minute", () => {
    // Arrange — the default fixture lesson is a few dozen words.
    const lesson = makeLesson();

    // Act / Assert
    expect(estimateReadingMinutes(lesson)).toBe(1);
  });

  it("estimates from the word count across all four phases and both bookends", () => {
    // Arrange — 660 words total at 220 wpm reads in exactly 3 minutes.
    const words = (count: number) => Array.from({ length: count }, (_, i) => `w${i}`).join(" ");
    const lesson = makeLesson({
      segments: {
        activate: { prose: words(200), visuals: [], claims: [], resources: [] },
        demonstrate: { prose: words(200), visuals: [], claims: [], resources: [] },
        apply: { prose: words(120), visuals: [], claims: [], resources: [] },
        integrate: { prose: words(120), visuals: [], claims: [], resources: [] },
      },
      expects: [words(10)],
      selfCheck: [words(10)],
    });

    // Act / Assert
    expect(estimateReadingMinutes(lesson)).toBe(3);
  });

  it("survives a lesson with entirely empty prose", () => {
    // Arrange
    const empty = { prose: "", visuals: [], claims: [], resources: [] };
    const lesson = makeLesson({
      segments: { activate: empty, demonstrate: empty, apply: empty, integrate: empty },
      expects: [],
      selfCheck: [],
    });

    // Act / Assert — never advertises "0 min read".
    expect(estimateReadingMinutes(lesson)).toBe(1);
  });
});
