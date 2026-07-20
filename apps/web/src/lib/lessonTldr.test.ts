import { describe, expect, it } from "vitest";

import type { Objective } from "../types/course";
import { deriveTldr } from "./lessonTldr";

function objective(statement: string): Objective {
  return { statement, bloomLevel: "understand", kc: "kc", assessedBy: [] };
}

describe("deriveTldr", () => {
  it("strips the objective scaffolding down to the capability", () => {
    // Arrange
    const objectives = [
      objective("Given a sorted array, locate a target with binary search."),
      objective(
        "Given examples of natural and Euclidean forms, the learner can explain why fractals" +
          " constitute a non-Euclidean geometry.",
      ),
    ];

    // Act / Assert
    expect(deriveTldr(objectives)).toEqual([
      "Locate a target with binary search.",
      "Explain why fractals constitute a non-Euclidean geometry.",
    ]);
  });

  it("keeps a statement without the scaffolding pattern intact", () => {
    expect(deriveTldr([objective("Fractals repeat at every scale.")])).toEqual([
      "Fractals repeat at every scale.",
    ]);
  });

  it("caps the summary at three bullets", () => {
    const objectives = ["one", "two", "three", "four"].map((n) => objective(`Statement ${n}.`));
    expect(deriveTldr(objectives)).toHaveLength(3);
  });

  it("returns nothing for a module without objectives", () => {
    expect(deriveTldr([])).toEqual([]);
  });
});
