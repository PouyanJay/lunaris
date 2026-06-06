import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LessonProse } from "./LessonProse";

const NO_MARKS = new Map<number, string>();

describe("LessonProse", () => {
  it("breaks a long single-string prose into multiple paragraphs", () => {
    const prose =
      "First sentence here. Second sentence here. Third sentence here. " +
      "Move 1: a new structural section starts. It continues on.";
    const { container } = render(
      <LessonProse
        prose={prose}
        sentenceMarks={NO_MARKS}
        activeClaimId={null}
        onSelectClaim={() => {}}
      />,
    );

    // The wall of text is segmented: a fixed 3-sentence cap + a cue ("Move 1:") force breaks.
    expect(container.querySelectorAll("p").length).toBeGreaterThan(1);
  });

  it("renders a matched sentence as a cross-link that selects its claim", () => {
    const onSelectClaim = vi.fn();
    const prose = "Plain opener sentence. The matched sentence lives here.";
    const marks = new Map<number, string>([[1, "demonstrate-0"]]);
    render(
      <LessonProse
        prose={prose}
        sentenceMarks={marks}
        activeClaimId={null}
        onSelectClaim={onSelectClaim}
      />,
    );

    const link = screen.getByRole("button", { name: /show the source note for/i });
    fireEvent.click(link);

    expect(onSelectClaim).toHaveBeenCalledWith("demonstrate-0");
    expect(screen.getByText("Plain opener sentence.")).toBeInTheDocument();
  });

  it("marks the active claim's sentence as pressed", () => {
    const prose = "Opener. The matched sentence lives here.";
    const marks = new Map<number, string>([[1, "demonstrate-0"]]);
    render(
      <LessonProse
        prose={prose}
        sentenceMarks={marks}
        activeClaimId="demonstrate-0"
        onSelectClaim={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: /show the source note for/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders empty prose without crashing", () => {
    const { container } = render(
      <LessonProse
        prose=""
        sentenceMarks={NO_MARKS}
        activeClaimId={null}
        onSelectClaim={() => {}}
      />,
    );
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});
