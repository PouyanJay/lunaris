import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AssessmentItem, Objective } from "../../types/course";
import type { LessonStep } from "./lessonSteps";
import { ChallengeStep } from "./ChallengeStep";

const OBJECTIVES: Objective[] = [
  {
    statement: "Given a sorted array, locate a target with binary search.",
    bloomLevel: "apply",
    kc: "binary_search",
    assessedBy: ["m0-i0"],
  },
];

function assessmentStep(items: AssessmentItem[]): LessonStep {
  return {
    id: "assessment:0",
    sectionId: "assessment",
    sectionLabel: "Check your understanding",
    kind: "assessment",
    assessment: items,
    words: 0,
  };
}

const ITEM: AssessmentItem = {
  id: "m0-i0",
  prompt: "Worst-case complexity of binary search?",
  objective: "binary_search",
  answer: "O(log n)",
  passCriterion: "States O(log n).",
};

describe("ChallengeStep — objective evidence", () => {
  it("evidences the assessed objective when the learner marks 'I got it'", () => {
    // Arrange
    const onEvidence = vi.fn();
    render(
      <ChallengeStep
        step={assessmentStep([ITEM])}
        objectives={OBJECTIVES}
        understoodObjectives={new Set()}
        onEvidenceObjective={onEvidence}
      />,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));
    fireEvent.click(screen.getByRole("button", { name: "I got it" }));

    // Assert — objective index 0 (kc binary_search) marked understood.
    expect(onEvidence).toHaveBeenCalledWith(0, true);
  });

  it("un-evidences on 'Not yet'", () => {
    // Arrange
    const onEvidence = vi.fn();
    render(
      <ChallengeStep
        step={assessmentStep([ITEM])}
        objectives={OBJECTIVES}
        understoodObjectives={new Set([0])}
        onEvidenceObjective={onEvidence}
      />,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // A prior "got it" (understood) shows the verdict, not the buttons.
    expect(screen.getByText(/you marked: got it/i)).toBeInTheDocument();
    expect(onEvidence).not.toHaveBeenCalled();
  });

  it("does not evidence an item mapping to no objective", () => {
    // Arrange — an item whose KC isn't among the module objectives.
    const onEvidence = vi.fn();
    const orphan = { ...ITEM, id: "m0-i9", objective: "unmapped_kc" };
    render(
      <ChallengeStep
        step={assessmentStep([orphan])}
        objectives={OBJECTIVES}
        understoodObjectives={new Set()}
        onEvidenceObjective={onEvidence}
      />,
    );

    // Act — self-grade still works locally, but writes no objective.
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));
    fireEvent.click(screen.getByRole("button", { name: "I got it" }));

    // Assert
    expect(onEvidence).not.toHaveBeenCalled();
    expect(screen.getByText(/you marked: got it/i)).toBeInTheDocument();
  });

  it("renders a check step as a single reflection challenge", () => {
    // Arrange
    const step: LessonStep = {
      id: "selfCheck:0",
      sectionId: "selfCheck",
      sectionLabel: "Self-check",
      kind: "check",
      items: ["Can you name the two signature properties of a fractal?"],
      words: 9,
    };

    // Act
    render(
      <ChallengeStep
        step={step}
        objectives={OBJECTIVES}
        understoodObjectives={new Set()}
        onEvidenceObjective={vi.fn()}
      />,
    );

    // Assert — one challenge, no model answer.
    expect(screen.getByText(/two signature properties/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check yourself/i })).toBeInTheDocument();
  });
});
