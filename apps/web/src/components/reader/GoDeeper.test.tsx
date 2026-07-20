import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GoDeeper } from "./GoDeeper";
import { Markdown } from "./Markdown";

describe("Markdown — :::deeper folds", () => {
  it("folds a deeper block closed under the Go-deeper summary", () => {
    // Arrange / Act
    render(
      <Markdown>
        {":::deeper[Why 'length' diverges]\nEach iteration multiplies total length by 4/3.\n:::"}
      </Markdown>,
    );

    // Assert — collapsed by default; the kicker + authored label form the summary.
    const summary = screen.getByText(/go deeper/i).closest("summary");
    expect(summary).toBeInTheDocument();
    expect(summary).toHaveTextContent(/why 'length' diverges/i);
    expect(summary?.closest("details")).not.toHaveAttribute("open");
  });

  it("renders native details/summary semantics without a label", () => {
    // Arrange / Act — the component's own contract, independent of the directive pipeline.
    render(<GoDeeper>Depth content.</GoDeeper>);

    // Assert — a collapsed native disclosure with the kicker as its summary.
    const summary = screen.getByText(/go deeper/i).closest("summary");
    expect(summary).toBeInTheDocument();
    expect(summary?.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Depth content.")).toBeInTheDocument();
  });

  it("renders a label-less deeper block with the kicker alone", () => {
    // Arrange / Act
    render(<Markdown>{":::deeper\nThe fuller derivation.\n:::"}</Markdown>);

    // Assert
    expect(screen.getByText(/go deeper/i)).toBeInTheDocument();
    expect(screen.getByText("The fuller derivation.")).toBeInTheDocument();
  });
});
