import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeCitation } from "../../test/fixtures";
import { AnnotationRail } from "./AnnotationRail";
import type { Annotation } from "./annotations";

function annotation(overrides: Partial<Annotation> = {}): Annotation {
  return {
    id: "demonstrate-0",
    phaseKey: "demonstrate",
    phaseLabel: "Strategies & worked example",
    claim: {
      text: "Comparison reduces the problem size each step.",
      supportedBy: "src-1",
      verifierStatus: "supported",
    },
    citation: makeCitation(),
    matchedSentence: 2,
    ...overrides,
  };
}

describe("AnnotationRail", () => {
  it("groups annotations under their teaching phase and shows status + source", () => {
    render(
      <AnnotationRail annotations={[annotation()]} activeClaimId={null} onSelect={() => {}} />,
    );

    expect(screen.getByText("Strategies & worked example")).toBeInTheDocument();
    expect(screen.getByText("SUPPORTED")).toBeInTheDocument();
    expect(screen.getByText("Comparison reduces the problem size each step.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CLRS" })).toHaveAttribute(
      "href",
      "https://example.org/clrs",
    );
  });

  it("calls onSelect with the annotation id when its entry is activated", () => {
    const onSelect = vi.fn();
    render(
      <AnnotationRail annotations={[annotation()]} activeClaimId={null} onSelect={onSelect} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /locate in the lesson/i }));

    expect(onSelect).toHaveBeenCalledWith("demonstrate-0");
  });

  it("marks the active entry as pressed", () => {
    render(
      <AnnotationRail
        annotations={[annotation()]}
        activeClaimId="demonstrate-0"
        onSelect={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: /locate in the lesson/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows the phase-fallback hint when a claim has no confident sentence match", () => {
    render(
      <AnnotationRail
        annotations={[annotation({ matchedSentence: null })]}
        activeClaimId={null}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByText(/linked to the .* section/i)).toBeInTheDocument();
  });

  it("shows a recovery line for a claim with no source on record", () => {
    const cut = annotation({
      claim: { text: "An ungrounded assertion.", supportedBy: null, verifierStatus: "cut" },
      citation: undefined,
      matchedSentence: null,
    });
    render(<AnnotationRail annotations={[cut]} activeClaimId={null} onSelect={() => {}} />);

    expect(screen.getByText("CUT")).toBeInTheDocument();
    expect(screen.getByText("No source on record")).toBeInTheDocument();
  });

  it("renders an empty note when the lesson has no claims", () => {
    render(<AnnotationRail annotations={[]} activeClaimId={null} onSelect={() => {}} />);

    expect(screen.getByText(/no claims to verify/i)).toBeInTheDocument();
  });

  it("surfaces the source's trust tier and credibility from the resolved citation", () => {
    const classified = annotation({
      citation: makeCitation({ trustTier: "reputable", credibility: 0.91 }),
    });
    render(<AnnotationRail annotations={[classified]} activeClaimId={null} onSelect={() => {}} />);

    // ClaimProvenance → SourceTrust renders the tier word (never colour alone) and the percentage.
    expect(screen.getByText("reputable")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
  });

  it("exposes a stable accessible region name", () => {
    render(
      <AnnotationRail annotations={[annotation()]} activeClaimId={null} onSelect={() => {}} />,
    );
    expect(screen.getByRole("complementary", { name: /sources and checks/i })).toBeInTheDocument();
  });
});
