import { describe, expect, it } from "vitest";

import { makeCourse, makeLesson } from "../test/fixtures";
import { buildGlossaryIndex } from "./glossaryIndex";

describe("buildGlossaryIndex", () => {
  it("indexes every knowledge component's label with its graph definition", () => {
    // Arrange / Act — the fixture graph defines comparison / sorted_order / binary_search.
    const index = buildGlossaryIndex(makeCourse());

    // Assert — keyed case-insensitively.
    expect(index.get("binary search")).toBe("Halving a sorted range each step.");
    expect(index.get("comparison")).toBe("Ordering two values.");
  });

  it("lets an authored :term directive override a graph definition for the same term", () => {
    // Arrange
    const course = makeCourse();
    const lesson = makeLesson();
    lesson.segments.activate.prose =
      'A :term[binary search]{title="The authored definition."} appears here.';
    course.modules[0]!.lessons = [lesson];

    // Act / Assert
    expect(buildGlossaryIndex(course).get("binary search")).toBe("The authored definition.");
  });

  it("skips knowledge components without a definition", () => {
    // Arrange
    const course = makeCourse();
    course.graph.nodes = [
      {
        id: "bare",
        label: "Bare Concept",
        definition: "",
        difficulty: 0.1,
        bloomCeiling: "apply",
        sources: [],
      },
    ];

    // Act / Assert
    expect(buildGlossaryIndex(course).has("bare concept")).toBe(false);
  });
});
