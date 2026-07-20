import { describe, expect, it } from "vitest";

import { highlightTerms } from "./transcriptHighlight";

describe("highlightTerms", () => {
  it("flags a key term, case-insensitively, and leaves the rest plain", () => {
    // Arrange / Act
    const segments = highlightTerms("A Coastline has no single length.", ["coastline"]);

    // Assert
    expect(segments).toEqual([
      { text: "A ", highlight: false },
      { text: "Coastline", highlight: true },
      { text: " has no single length.", highlight: false },
    ]);
  });

  it("matches a multi-word term as a phrase", () => {
    // Arrange / Act
    const segments = highlightTerms("no single characteristic length captures it", [
      "characteristic length",
    ]);

    // Assert
    expect(segments.filter((s) => s.highlight).map((s) => s.text)).toEqual([
      "characteristic length",
    ]);
  });

  it("does not highlight a term that is only a partial word", () => {
    // Arrange / Act — "art" must not match inside "parts".
    const segments = highlightTerms("Parts resemble the whole.", ["art"]);

    // Assert
    expect(segments).toEqual([{ text: "Parts resemble the whole.", highlight: false }]);
  });

  it("returns a single plain segment when there are no terms", () => {
    // Arrange / Act / Assert
    expect(highlightTerms("Plain caption.", [])).toEqual([
      { text: "Plain caption.", highlight: false },
    ]);
  });

  it("is loss-less — the segments reproduce the input", () => {
    // Arrange
    const text = "Zoom into the koch curve to see self-similarity.";

    // Act
    const segments = highlightTerms(text, ["koch curve", "zoom"]);

    // Assert
    expect(segments.map((s) => s.text).join("")).toBe(text);
    expect(segments.filter((s) => s.highlight).map((s) => s.text)).toEqual(["Zoom", "koch curve"]);
  });
});
