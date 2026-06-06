import { render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("prose structure — enumerations & sections", () => {
  it("turns an inline (1)/(2)/(3) enumeration into an ordered list with its lead-in preserved", () => {
    const prose =
      "Three interlocking moves: (1) upgrade vocabulary from general to discipline-specific; " +
      "(2) use subordination and embedding to show logical relationships in a single sentence; " +
      "(3) calibrate register (word choice, voice, complexity) to match your audience and genre.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const list = container.querySelector("ol");
    expect(list).not.toBeNull();
    const items = within(list as HTMLElement).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent(/^upgrade vocabulary from general to discipline-specific$/);
    // The trailing parenthetical in item 3 is NOT mistaken for a marker.
    expect(items[2]).toHaveTextContent(/calibrate register \(word choice, voice, complexity\)/);
    // The lead-in stays as prose above the list, with its markers gone.
    expect(container.textContent).toContain("Three interlocking moves:");
    expect(container.textContent).not.toContain("(1)");
  });

  it("renders an (a)/(b)/(c) enumeration as an alpha-marked ordered list", () => {
    const prose =
      "To upgrade: (a) read recent peer-reviewed articles; (b) note terms that appear repeatedly; " +
      "(c) cross-check against a discipline-specific glossary.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const list = container.querySelector("ol");
    expect(list).toHaveAttribute("type", "a");
    expect(within(list as HTMLElement).getAllByRole("listitem")).toHaveLength(3);
  });

  it("leaves an ordinary paragraph (no enumeration) untouched", () => {
    const prose = "A sentence with one independent clause (and an aside) cannot express much.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelector("p")?.textContent).toBe(prose);
  });

  it("groups labelled 'Move N:' paragraphs into collapsible sections headed by their label", () => {
    const prose =
      "Move 1: Specialized vocabulary. Generalist dictionaries list one definition per word.\n\n" +
      "Move 2: Strategic subordination. A sentence with one clause cannot express complex reasoning.\n\n" +
      "Move 3: Calibrate register. Match word choice to your audience.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const sections = container.querySelectorAll("details");
    expect(sections).toHaveLength(3);
    // Each section is a collapsible headed by its label + title; open by default so nothing hides.
    const first = sections[0] as HTMLDetailsElement;
    expect(first.open).toBe(true);
    expect(first.querySelector("summary")?.textContent).toBe("Move 1: Specialized vocabulary");
    expect(first.querySelector("summary")?.tagName).toBe("SUMMARY");
    expect(first).toHaveTextContent("Generalist dictionaries list one definition per word.");
  });

  it("does not sectionize a lone labelled paragraph (needs a real section run)", () => {
    const prose = "Step 1: Do the thing. Then keep reading as normal prose without a second step.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(container.querySelector("details")).toBeNull();
    expect(container.querySelector("p")?.textContent).toContain("Step 1: Do the thing.");
  });

  it("splits an enumeration that lives inside a labelled section's body", () => {
    const prose =
      "Move 1: Specialized vocabulary. To upgrade: (1) read articles; (2) note recurring terms.\n\n" +
      "Move 2: Strategic subordination. Use subordinate clauses to show logic.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const section = container.querySelector("details");
    expect(section).not.toBeNull();
    const list = within(section as HTMLElement).getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});
