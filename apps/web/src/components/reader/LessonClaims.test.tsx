import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCitation } from "../../test/fixtures";
import type { Citation, Claim } from "../../types/course";
import { LessonClaims } from "./LessonClaims";

function supportedClaim(citationId = "src-1"): Claim {
  return {
    text: "Comparison reduces the problem size each step.",
    supportedBy: citationId,
    verifierStatus: "supported",
  };
}

describe("LessonClaims", () => {
  it("renders a supported claim with its source and trust tier + credibility", () => {
    // Arrange / Act — a high-credibility, classified citation.
    const citations = new Map([
      ["src-1", makeCitation({ trustTier: "official", credibility: 0.91 })],
    ]);
    render(<LessonClaims claims={[supportedClaim()]} citations={citations} />);

    // Assert — the status, the source link, and the trust tier (in the word) + credibility percentage.
    expect(screen.getByText("SUPPORTED")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CLRS" })).toHaveAttribute(
      "href",
      "https://example.org/clrs",
    );
    expect(screen.getByText("official")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
  });

  it("flags low-credibility evidence without relying on colour alone", () => {
    // Arrange / Act — open-web evidence below the display threshold.
    const citations = new Map([["src-1", makeCitation({ trustTier: "open", credibility: 0.62 })]]);
    render(<LessonClaims claims={[supportedClaim()]} citations={citations} />);

    // Assert — the low state is carried BOTH by the accessible name AND a visible ⚠ glyph
    // (so it's never colour alone), with the percentage still readable.
    expect(screen.getByText("open")).toBeInTheDocument();
    const score = screen.getByLabelText("Credibility 62%, low");
    expect(score).toBeInTheDocument();
    expect(score.textContent).toContain("⚠");
  });

  it("shows the tier but no percentage when credibility is absent", () => {
    // Arrange / Act — a classified source with no credibility score (e.g. tier-only provenance).
    const citations = new Map([
      ["src-1", makeCitation({ trustTier: "official", credibility: null })],
    ]);
    render(<LessonClaims claims={[supportedClaim()]} citations={citations} />);

    // Assert — the tier word renders, but no percentage badge.
    expect(screen.getByText("official")).toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
  });

  it("renders a pre-P6.0 citation (no classification) without a trust badge", () => {
    // Arrange / Act — a citation that predates trust scoring (the trust fields are simply absent):
    // the source shows, but no tier/credibility.
    const bare: Citation = {
      id: "src-1",
      title: "CLRS",
      url: "https://example.org/clrs",
      snippet: "…",
    };
    render(<LessonClaims claims={[supportedClaim()]} citations={new Map([["src-1", bare]])} />);

    // Assert — the source survives, but no trust word/percentage is shown.
    expect(screen.getByRole("link", { name: "CLRS" })).toBeInTheDocument();
    expect(screen.queryByText("reputable")).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
  });

  it("shows a recovery line for a claim with no source on record", () => {
    // Arrange / Act — an unsupported claim (no citation id).
    const claim: Claim = {
      text: "An ungrounded assertion.",
      supportedBy: null,
      verifierStatus: "cut",
    };
    render(<LessonClaims claims={[claim]} citations={new Map()} />);

    // Assert
    expect(screen.getByText("CUT")).toBeInTheDocument();
    expect(screen.getByText("No source on record")).toBeInTheDocument();
  });
});
