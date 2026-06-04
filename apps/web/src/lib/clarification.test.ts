import { describe, expect, it } from "vitest";

import type { Clarifier } from "../types/clarifier";
import { answersToClarification, recommendedAnswers } from "./clarification";

const CLARIFIER: Clarifier = {
  questions: [
    {
      id: "level",
      prompt: "?",
      kind: "choice",
      placeholder: "",
      options: [
        { value: "novice", label: "Beginner", recommended: false },
        { value: "advanced", label: "Advanced", recommended: true },
      ],
    },
    { id: "knowledge", prompt: "?", kind: "text", placeholder: "everyday English", options: [] },
    { id: "background", prompt: "?", kind: "text", placeholder: "what you do", options: [] },
    {
      id: "detail",
      prompt: "?",
      kind: "choice",
      placeholder: "",
      options: [
        { value: "balanced", label: "Balanced", recommended: true },
        { value: "in_depth", label: "In-depth", recommended: false },
      ],
    },
    {
      id: "language",
      prompt: "?",
      kind: "choice",
      placeholder: "",
      options: [{ value: "balanced", label: "Balanced", recommended: true }],
    },
  ],
};

describe("recommendedAnswers", () => {
  it("pre-picks the recommended option for choices and leaves text empty", () => {
    expect(recommendedAnswers(CLARIFIER)).toEqual({
      level: "advanced",
      knowledge: "",
      background: "",
      detail: "balanced",
      language: "balanced",
    });
  });

  it("falls back to the first option when none is recommended", () => {
    const clarifier: Clarifier = {
      questions: [
        {
          id: "level",
          prompt: "?",
          kind: "choice",
          placeholder: "",
          options: [
            { value: "novice", label: "Beginner", recommended: false },
            { value: "expert", label: "Expert", recommended: false },
          ],
        },
      ],
    };

    expect(recommendedAnswers(clarifier).level).toBe("novice");
  });
});

describe("answersToClarification", () => {
  it("maps confirmed answers onto the typed clarification (trimming text)", () => {
    const clarification = answersToClarification({
      level: "advanced",
      knowledge: "  solid grammar  ",
      background: "a nurse",
      detail: "in_depth",
      language: "sophisticated",
    });

    expect(clarification).toEqual({
      targetLevel: "advanced",
      assumedKnown: "solid grammar",
      background: "a nurse",
      detailDepth: "in_depth",
      languageStyle: "sophisticated",
    });
  });

  it("omits empty/whitespace text so confirming the inference verbatim is the identity", () => {
    const clarification = answersToClarification({
      level: "advanced",
      knowledge: "   ",
      background: "",
      detail: "balanced",
      language: "balanced",
    });

    // Only the (harmless, same-value) CHOICE overrides ride along; no text appends.
    expect(clarification).toEqual({
      targetLevel: "advanced",
      detailDepth: "balanced",
      languageStyle: "balanced",
    });
  });
});
