import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhraseMark } from "./annotations";
import { LessonProse } from "./LessonProse";

const NO_MARKS: PhraseMark[] = [];

describe("LessonProse", () => {
  it("renders Markdown prose as rich text, not literal markers", () => {
    const prose = "The strategy is *source with purpose* and **draft with anchors**.";
    const { container } = render(
      <LessonProse prose={prose} marks={NO_MARKS} activeClaimId={null} onSelectClaim={() => {}} />,
    );

    expect(container.textContent).not.toContain("*");
    expect(container.querySelector("em")?.textContent).toBe("source with purpose");
    expect(container.querySelector("strong")?.textContent).toBe("draft with anchors");
  });

  it("renders Markdown lists", () => {
    render(
      <LessonProse
        prose={"Steps:\n\n- alpha\n- beta"}
        marks={NO_MARKS}
        activeClaimId={null}
        onSelectClaim={() => {}}
      />,
    );

    expect(screen.getByText("alpha").closest("ul")).not.toBeNull();
  });

  it("tags the block containing a matched claim and selects it via the marker", () => {
    const onSelectClaim = vi.fn();
    const prose = "Plain opener sentence. The matched sentence lives in this paragraph.";
    const marks: PhraseMark[] = [
      { claimId: "demonstrate-0", text: "The matched sentence lives in this paragraph." },
    ];
    const { container } = render(
      <LessonProse
        prose={prose}
        marks={marks}
        activeClaimId={null}
        onSelectClaim={onSelectClaim}
      />,
    );

    // The containing paragraph is tagged as the cross-link target.
    expect(container.querySelector('[data-claim-id="demonstrate-0"]')).not.toBeNull();

    // Its marker selects the claim (bidirectional → rail).
    const marker = screen.getByRole("button", { name: /show the source note for/i });
    fireEvent.click(marker);
    expect(onSelectClaim).toHaveBeenCalledWith("demonstrate-0");
  });

  it("marks the active claim's block as pressed", () => {
    const prose = "Opener. The matched sentence lives here in this paragraph.";
    const marks: PhraseMark[] = [
      { claimId: "demonstrate-0", text: "The matched sentence lives here in this paragraph." },
    ];
    render(
      <LessonProse
        prose={prose}
        marks={marks}
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
      <LessonProse prose="" marks={NO_MARKS} activeClaimId={null} onSelectClaim={() => {}} />,
    );
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});
