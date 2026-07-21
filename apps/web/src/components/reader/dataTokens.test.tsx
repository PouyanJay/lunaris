import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** R2 — recognise domain/data tokens by SHAPE (not a subject dictionary) and render them as neutral
 *  monospace chips: the "data is the typographic signature" rule. Never accent-toned. */
describe("data tokens (R2)", () => {
  it.each([
    ["internal-digit id", "The cytokine IL-5 recruits eosinophils.", "IL-5"],
    ["hyphen-digit id", "Release of IL-33 follows the trigger.", "IL-33"],
    ["short mixed id", "The Th2 axis dominates here.", "Th2"],
    ["caps+digit id", "ILC2 cells are innate.", "ILC2"],
    ["all-caps acronym", "Epithelium releases TSLP quickly.", "TSLP"],
    ["mixed-case token", "It drives IgE class switching.", "IgE"],
    ["number-unit token", "For the 600-eosinophil patient above.", "600-eosinophil"],
  ])("chips a %s as a neutral data chip", (_label, prose, token) => {
    render(<Markdown>{prose}</Markdown>);
    const chip = screen.getByText(token);
    expect(chip).toHaveAttribute("data-category", "data");
    expect(chip.className).toMatch(/mono/);
  });

  it("chips the reference wall's cytokine tokens", () => {
    render(<Markdown>{"CANONICAL CYTOKINES: three core cytokines are IL-4, IL-5, and IL-13."}</Markdown>);
    for (const t of ["IL-4", "IL-5", "IL-13"]) {
      expect(screen.getByText(t)).toHaveAttribute("data-category", "data");
    }
  });

  describe("does NOT fire (conservative)", () => {
    it("leaves ordinary lowercase words unchipped", () => {
      const { container } = render(
        <Markdown>{"the cells release proteins that damage tissue over time."}</Markdown>,
      );
      expect(container.querySelector('[data-category="data"]')).toBeNull();
    });

    it("does not chip a bare number or a plain year", () => {
      const { container } = render(<Markdown>{"By 2024 the type 2 response was mapped."}</Markdown>);
      expect(container.querySelector('[data-category="data"]')).toBeNull();
      expect(container.textContent).toContain("2024");
      expect(container.textContent).toContain("type 2");
    });

    it("does not chip an all-caps emphasis word", () => {
      const { container } = render(<Markdown>{"This is REALLY the whole point here."}</Markdown>);
      expect(container.querySelector('[data-category="data"]')).toBeNull();
    });
  });
});
