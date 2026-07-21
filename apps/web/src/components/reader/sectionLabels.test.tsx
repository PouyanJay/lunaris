import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ASTHMA_PROSE } from "./lessonProse.fixture";
import { Markdown } from "./Markdown";

describe("section labels (R1)", () => {
  it("lifts a leading ALL-CAPS 'LABEL:' into an eyebrow section head, body preserved verbatim", () => {
    const { container } = render(
      <Markdown>{"STRATEGY: Build the cascade from the airway surface downward."}</Markdown>,
    );

    const label = screen.getByRole("heading", { name: /strategy/i });
    expect(label.textContent).toContain("STRATEGY");
    expect(label.textContent).not.toContain(":");

    expect(container.textContent).toContain("Build the cascade from the airway surface downward.");
    expect(label.textContent).not.toContain("Build the cascade");
  });

  it("keeps a '(qualifier)' as a separate muted span on the label", () => {
    render(<Markdown>{"UPSTREAM LAYER (alarmins): epithelial cells release alarmins."}</Markdown>);

    const label = screen.getByRole("heading", { name: /upstream layer/i });
    expect(within(label).getByText("alarmins")).toBeInTheDocument();
    expect(label.textContent).toContain("UPSTREAM LAYER");
  });

  it("splits a wall carrying several inline labels into one section head each", () => {
    render(<Markdown>{ASTHMA_PROSE}</Markdown>);

    for (const name of [
      /strategy/i,
      /upstream layer/i,
      /canonical cytokines/i,
      /worked attribution/i,
      /eosinophil effector role/i,
      /structural chain/i,
      /worked example/i,
    ]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
  });

  it("preserves the sentence before an inline label as its own body, not swallowed by the head", () => {
    render(
      <Markdown>
        {"STRATEGY: build downward, then stop. CANONICAL CYTOKINES: three core cytokines exist."}
      </Markdown>,
    );

    const second = screen.getByRole("heading", { name: /canonical cytokines/i });
    // The prior sentence stays out of the second head.
    expect(second.textContent).not.toContain("stop");
    expect(screen.getByText(/build downward, then stop\./)).toBeInTheDocument();
    expect(screen.getByText(/three core cytokines exist\./)).toBeInTheDocument();
  });

  it("preserves the full wording of the reformatted wall (presentation-only)", () => {
    const { container } = render(<Markdown>{ASTHMA_PROSE}</Markdown>);
    const flat = (container.textContent ?? "").replace(/\s+/g, " ").trim();
    // Every non-label sentence body survives verbatim.
    expect(flat).toContain("Build the T2 inflammatory cascade from the airway surface downward");
    expect(flat).toContain("each node is a druggable biologic target");
    expect(flat).toContain("When triggers strike the airway epithelium");
  });

  describe("does NOT fire (conservative)", () => {
    it("leaves an ordinary capitalised sentence alone", () => {
      render(<Markdown>{"The T2 axis produces three cytokines that drive disease."}</Markdown>);
      expect(screen.queryByRole("heading")).toBeNull();
    });

    it("does not treat a lone single capital + colon as a label", () => {
      render(<Markdown>{"A: the first option is not a section label at all."}</Markdown>);
      expect(screen.queryByRole("heading")).toBeNull();
    });

    it("defers a 'NOTE:' lead-in to the callout system, not a section label", () => {
      render(<Markdown>{"NOTE: keep the airway open during the procedure."}</Markdown>);
      // Handled by the callout lift (complementary region), never a section heading.
      expect(screen.queryByRole("heading")).toBeNull();
      expect(screen.getByRole("complementary")).toBeInTheDocument();
    });
  });
});
