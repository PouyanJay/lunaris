import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AssessmentItem } from "../../types/course";
import { LessonAssessment } from "./LessonAssessment";

function item(overrides: Partial<AssessmentItem> = {}): AssessmentItem {
  return {
    id: "i0",
    prompt: "Design a fault-tolerant VPC for a 3-tier web app.",
    objective: "vpc",
    answer: null,
    passCriterion: "",
    ...overrides,
  };
}

describe("lesson assessment", () => {
  it("renders the pass criterion with its 'Passes when' label when present", () => {
    render(
      <LessonAssessment
        items={[item({ passCriterion: "Spans >=2 AZs; no single point of failure." })]}
      />,
    );

    // The prompt and its concrete, gradeable bar are both shown, and the label sits within the same
    // criterion line as the bar (so the learner reads what a passing response must clear, labelled).
    expect(screen.getByText("Design a fault-tolerant VPC for a 3-tier web app.")).toBeVisible();
    const criterion = screen.getByText(/Spans >=2 AZs/);
    expect(criterion).toBeVisible();
    expect(criterion).toHaveTextContent(/passes when/i);
  });

  it("omits the criterion line for a pre-P4 item with no pass criterion", () => {
    render(<LessonAssessment items={[item({ passCriterion: "" })]} />);

    // The prompt still renders; no empty "Passes when" line leaks in.
    expect(screen.getByText("Design a fault-tolerant VPC for a 3-tier web app.")).toBeVisible();
    expect(screen.queryByText(/passes when/i)).toBeNull();
  });
});
