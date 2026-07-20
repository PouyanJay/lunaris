import { describe, expect, it } from "vitest";

import type { Resource } from "../types/course";
import { matchResourcesToChapters } from "./chapterResources";
import type { VideoChapter } from "./videoJobs";

function chapter(id: string, title: string, keyTerms: string[]): VideoChapter {
  return { id, title, startS: 0, endS: 1, keyTerms };
}

function resource(title: string, why: string): Resource {
  return {
    kind: "article",
    title,
    url: `https://example.org/${encodeURIComponent(title)}`,
    source: "example.org",
    why,
    trustTier: "open",
    credibility: 0.5,
    duration: null,
    fetchedAt: "2026-07-01T00:00:00Z",
    author: null,
  };
}

describe("matchResourcesToChapters", () => {
  it("docks a resource under the chapter whose key terms it best covers", () => {
    // Arrange
    const chapters = [
      chapter("S1", "The coastline puzzle", ["coastline", "length"]),
      chapter("S2", "Self-similarity", ["koch curve", "zoom"]),
    ];
    const resources = [resource("Koch curve zoom", "Watch the koch curve under zoom")];

    // Act
    const { byChapter, unmatched } = matchResourcesToChapters(chapters, resources);

    // Assert — shares koch/curve/zoom with S2, nothing with S1.
    expect(unmatched).toEqual([]);
    expect(byChapter.get("S2")?.map((s) => s.resource.title)).toEqual(["Koch curve zoom"]);
    expect(byChapter.get("S1") ?? []).toEqual([]);
  });

  it("scores rel as the share of the chapter's terms the resource covers", () => {
    // Arrange — chapter terms {cost, logarithm, halving}; the resource covers only "halving".
    const chapters = [chapter("S1", "Cost", ["logarithm", "halving"])];
    const resources = [resource("Halving explained", "how halving works")];

    // Act
    const { byChapter } = matchResourcesToChapters(chapters, resources);

    // Assert — 1 of 3 terms ≈ 33%.
    expect(byChapter.get("S1")?.[0]?.rel).toBe(33);
  });

  it("returns a resource that shares no term with any chapter as unmatched", () => {
    // Arrange
    const chapters = [chapter("S1", "Coastlines", ["coastline"])];
    const resources = [resource("Unrelated", "about databases")];

    // Act
    const { byChapter, unmatched } = matchResourcesToChapters(chapters, resources);

    // Assert
    expect(unmatched.map((r) => r.title)).toEqual(["Unrelated"]);
    expect(byChapter.get("S1") ?? []).toEqual([]);
  });

  it("assigns each resource to a single best chapter, ties to the earlier", () => {
    // Arrange — both chapters cover the shared term equally.
    const chapters = [chapter("S1", "Alpha", ["shared"]), chapter("S2", "Beta", ["shared"])];
    const resources = [resource("Shared thing", "the shared thing")];

    // Act
    const { byChapter } = matchResourcesToChapters(chapters, resources);

    // Assert — earlier chapter wins the tie; the resource is docked once.
    expect(byChapter.get("S1")?.map((s) => s.resource.title)).toEqual(["Shared thing"]);
    expect(byChapter.get("S2") ?? []).toEqual([]);
  });

  it("orders a chapter's resources most-relevant first", () => {
    // Arrange — one resource fully covers the chapter's terms, one only partially.
    const chapters = [chapter("S1", "Fractal dimension", ["fractal", "dimension"])];
    const resources = [
      resource("Dimension only", "the dimension idea"),
      resource("Fractal dimension deep dive", "fractal dimension explained"),
    ];

    // Act
    const { byChapter } = matchResourcesToChapters(chapters, resources);

    // Assert — the fuller-coverage resource ranks first.
    expect(byChapter.get("S1")?.map((s) => s.resource.title)).toEqual([
      "Fractal dimension deep dive",
      "Dimension only",
    ]);
  });
});
