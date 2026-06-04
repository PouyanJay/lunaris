import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TrustTier } from "../../types/course";
import { SourceTrust } from "./SourceTrust";

describe("SourceTrust", () => {
  it.each<TrustTier>(["official", "reputable", "open", "blocked"])(
    "renders the %s tier as a word (never colour alone)",
    (tier) => {
      // Arrange / Act
      render(<SourceTrust tier={tier} credibility={0.8} />);

      // Assert — the tier is shown in the WORD and carries the data-tier hook for its colour.
      const word = screen.getByText(tier);
      expect(word).toBeInTheDocument();
      expect(word).toHaveAttribute("data-tier", tier);
    },
  );

  it("shows the credibility percentage when present", () => {
    // Arrange / Act
    render(<SourceTrust tier="official" credibility={0.91} />);

    // Assert
    expect(screen.getByText("91%")).toBeInTheDocument();
  });

  it.each<[string, number | null]>([
    ["null (absent)", null],
    ["zero score", 0],
  ])("hides the percentage when credibility is %s", (_label, credibility) => {
    // Arrange / Act
    render(<SourceTrust tier="open" credibility={credibility} />);

    // Assert — the tier still shows, but no percentage badge.
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
  });

  it("flags low credibility with a ⚠ glyph and an accessible 'low' name", () => {
    // Arrange / Act — below the threshold.
    render(<SourceTrust tier="open" credibility={0.62} lowBelow={0.7} />);

    // Assert — both the visible glyph and the accessible name carry the state (not colour alone).
    const score = screen.getByLabelText("Credibility 62%, low");
    expect(score.textContent).toContain("⚠");
  });

  it("does not flag credibility exactly at the threshold (strict below)", () => {
    // Arrange / Act — equal to the threshold is NOT low.
    render(<SourceTrust tier="open" credibility={0.7} lowBelow={0.7} />);

    // Assert
    expect(screen.getByLabelText("Credibility 70%")).toBeInTheDocument();
    expect(screen.queryByLabelText(/, low/)).not.toBeInTheDocument();
  });

  it("never flags low without a threshold (resources opt out)", () => {
    // Arrange / Act — no lowBelow: a weak score still shows plainly, no ⚠.
    render(<SourceTrust tier="open" credibility={0.1} />);

    // Assert
    const score = screen.getByLabelText("Credibility 10%");
    expect(score.textContent).not.toContain("⚠");
  });
});
