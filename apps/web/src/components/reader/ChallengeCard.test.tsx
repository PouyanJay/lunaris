import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AssessmentItem } from "../../types/course";
import { ChallengeCard } from "./ChallengeCard";

const ITEM: AssessmentItem = {
  id: "m0-i0",
  prompt: "What is the worst-case time complexity of binary search?",
  objective: "binary_search",
  answer: "O(log n)",
  passCriterion: "States O(log n) and explains the halving of the search space.",
};

describe("ChallengeCard — assessment", () => {
  it("presents the prompt first and hides the answer behind a reveal", () => {
    // Arrange / Act
    render(
      <ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} criterion={ITEM.passCriterion} />,
    );

    // Assert — the question and an attempt input are shown; the model answer is not.
    expect(screen.getByText(ITEM.prompt)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeInTheDocument();
    expect(screen.queryByText("O(log n)")).not.toBeInTheDocument();
    expect(screen.queryByText(/passes when/i)).not.toBeInTheDocument();
  });

  it("reveals the model answer and pass criterion on demand", () => {
    // Arrange
    render(
      <ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} criterion={ITEM.passCriterion} />,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert — the explanation into the gap.
    expect(screen.getByText("O(log n)")).toBeInTheDocument();
    expect(screen.getByText(/halving of the search space/i)).toBeInTheDocument();
  });

  it("surfaces a soft echo hint when the attempt shares a word with the answer", () => {
    // Arrange
    render(
      <ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} criterion={ITEM.passCriterion} />,
    );

    // Act — commit an attempt that echoes "log", then reveal.
    fireEvent.change(screen.getByRole("textbox", { name: /your answer/i }), {
      target: { value: "It runs in log n time." },
    });
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert — assistance, phrased as a hint (never a verdict).
    expect(screen.getByText(/your answer mentions/i)).toHaveTextContent("log");
  });

  it("records the learner's self-grade through onGrade", () => {
    // Arrange
    const onGrade = vi.fn();
    render(
      <ChallengeCard
        prompt={ITEM.prompt}
        answer={ITEM.answer}
        criterion={ITEM.passCriterion}
        onGrade={onGrade}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Act
    fireEvent.click(screen.getByRole("button", { name: "I got it" }));

    // Assert
    expect(onGrade).toHaveBeenCalledWith("got-it");
  });

  it("shows the prior verdict instead of the grade buttons on a revisited challenge", () => {
    // Arrange / Act
    render(
      <ChallengeCard
        prompt={ITEM.prompt}
        answer={ITEM.answer}
        criterion={ITEM.passCriterion}
        onGrade={vi.fn()}
        grade="got-it"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert
    expect(screen.getByText(/you marked: got it/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I got it" })).not.toBeInTheDocument();
  });

  it("announces the revealed answer through a live region", () => {
    // Arrange
    render(
      <ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} criterion={ITEM.passCriterion} />,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert — the reveal is a polite live region so AT users hear the answer appear.
    const reveal = screen.getByRole("region", { name: /the answer/i });
    expect(reveal).toHaveAttribute("aria-live", "polite");
  });

  it("omits the answer block for a bare self-check reflection", () => {
    // Arrange / Act — no answer/criterion (a self-check string); the commit control adapts.
    render(<ChallengeCard prompt="Can you locate 7 in at most 4 comparisons?" onGrade={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /check yourself/i }));

    // Assert — reflection reveals no model answer, but still lets the learner self-report.
    expect(screen.queryByText(/passes when/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I got it" })).toBeInTheDocument();
  });

  it("hides the self-grade step when no grader is wired (read-only context)", () => {
    // Arrange / Act — no onGrade (offline / no progress).
    render(<ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} />);
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert — the answer reveals, but there is nothing to self-report into.
    expect(screen.getByText("O(log n)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I got it" })).not.toBeInTheDocument();
  });

  it("shows an answer with no pass criterion cleanly", () => {
    // Arrange / Act — a pre-P4 item: answer present, criterion empty.
    render(<ChallengeCard prompt={ITEM.prompt} answer="42" criterion="" />);
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText(/passes when/i)).not.toBeInTheDocument();
  });

  it("does not falsely hint when the attempt shares no distinctive word", () => {
    // Arrange
    render(
      <ChallengeCard prompt={ITEM.prompt} answer={ITEM.answer} criterion={ITEM.passCriterion} />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: /your answer/i }), {
      target: { value: "I have no idea." },
    });

    // Act
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));

    // Assert
    expect(screen.queryByText(/your answer mentions/i)).not.toBeInTheDocument();
  });
});
