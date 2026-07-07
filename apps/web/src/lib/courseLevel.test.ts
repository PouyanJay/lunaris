import { describe, expect, it } from "vitest";

import { bucketLevel } from "./courseLevel";

const node = (difficulty: number) => ({ difficulty });

describe("bucketLevel", () => {
  // Mirrors the server buckets (apps/api lunaris_api/library/derive_course_summary.py, AD3):
  // mean < 0.34 beginner, < 0.67 intermediate, else advanced — boundaries inclusive upward.
  it.each([
    [[0.0, 0.2], "beginner"],
    [[0.33], "beginner"],
    [[0.34], "intermediate"],
    [[0.2, 0.8], "intermediate"],
    [[0.66], "intermediate"],
    [[0.67], "advanced"],
    [[0.9, 1.0], "advanced"],
  ])("buckets mean difficulty of %j as %s", (difficulties, expected) => {
    expect(bucketLevel(difficulties.map(node))).toBe(expected);
  });

  it("returns null for a graphless course — never an invented level", () => {
    expect(bucketLevel([])).toBeNull();
  });
});
