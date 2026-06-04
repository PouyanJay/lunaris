import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SourceEvaluation } from "../../types/course";
import { DiscoverySources } from "./DiscoverySources";

function source(overrides: Partial<SourceEvaluation> = {}): SourceEvaluation {
  return {
    kcId: "dijkstra",
    domain: "study.example",
    trustTier: "reputable",
    credibility: 0.75,
    sourceType: "web",
    accepted: true,
    reason: "On topic.",
    ...overrides,
  };
}

describe("DiscoverySources", () => {
  it("renders each vetted source with its domain, trust, verdict, and reason", () => {
    render(
      <DiscoverySources
        sources={[
          source({ domain: "study.example", accepted: true, reason: "On topic." }),
          source({
            kcId: "heaps",
            domain: "spam.example",
            trustTier: "open",
            credibility: 0.3,
            accepted: false,
            reason: "Off topic.",
          }),
        ]}
      />,
    );

    // Each row carries its domain, reason, the trust tier word (never colour-alone, via SourceTrust),
    // and the visible keep/skip glyph.
    const keptRow = screen.getByText("study.example").closest("li") as HTMLElement;
    expect(within(keptRow).getByText("On topic.")).toBeInTheDocument();
    expect(within(keptRow).getByText("reputable")).toBeInTheDocument();
    expect(within(keptRow).getByText("✓")).toBeInTheDocument();

    const skippedRow = screen.getByText("spam.example").closest("li") as HTMLElement;
    expect(within(skippedRow).getByText("Off topic.")).toBeInTheDocument();
    expect(within(skippedRow).getByText("open")).toBeInTheDocument();
    expect(within(skippedRow).getByText("✕")).toBeInTheDocument();
  });

  it("heads the table with a kept/skipped tally", () => {
    render(
      <DiscoverySources
        sources={[
          source({ accepted: true }),
          source({ domain: "a.example", accepted: false }),
          source({ domain: "b.example", accepted: false }),
        ]}
      />,
    );

    expect(screen.getByText("1 kept · 2 skipped")).toBeInTheDocument();
  });

  it("shows 'unrated' when a source has no trust tier", () => {
    render(<DiscoverySources sources={[source({ trustTier: null, credibility: null })]} />);

    expect(screen.getByText("unrated")).toBeInTheDocument();
  });

  it("labels the verdict for assistive tech, not by colour alone", () => {
    render(<DiscoverySources sources={[source({ domain: "study.example", accepted: false })]} />);

    const row = screen.getByText("study.example").closest("li");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText(/skipped:/i)).toBeInTheDocument();
  });
});
