import { describe, expect, it } from "vitest";

import { applyComposerLevel, composerLevelToTarget } from "./composerLevel";

describe("composerLevelToTarget", () => {
  it("maps concrete choices onto clarifier levels and leaves 'recommended' to inference", () => {
    expect(composerLevelToTarget("beginner")).toBe("novice");
    expect(composerLevelToTarget("intermediate")).toBe("intermediate");
    expect(composerLevelToTarget("advanced")).toBe("advanced");
    expect(composerLevelToTarget("recommended")).toBeUndefined();
  });
});

describe("applyComposerLevel", () => {
  it("overrides the target level on an existing clarification without dropping its other answers", () => {
    const base = { assumedKnown: "the basics", targetLevel: "novice" as const };
    expect(applyComposerLevel(base, "advanced")).toEqual({
      assumedKnown: "the basics",
      targetLevel: "advanced",
    });
  });

  it("builds a level-only clarification when there is no brief loaded", () => {
    expect(applyComposerLevel(undefined, "beginner")).toEqual({ targetLevel: "novice" });
  });

  it("leaves the clarification untouched for 'recommended' (inference-only build)", () => {
    expect(applyComposerLevel(undefined, "recommended")).toBeUndefined();
    const base = { assumedKnown: "x" };
    expect(applyComposerLevel(base, "recommended")).toBe(base);
  });
});
