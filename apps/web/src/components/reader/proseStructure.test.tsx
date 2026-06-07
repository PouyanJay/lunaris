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

  it("still lifts an (a)/(b)/(c) enumeration that follows an example quote in the same paragraph", () => {
    // The example cue ("write: '…'") splits the paragraph; the continuation holding the markers must
    // still be re-scanned so the enumeration becomes a list rather than surviving as inline text.
    const prose =
      "To attribute a source, you might write: 'Source A claims that transit reduces congestion.' " +
      "Then build a three-part structure: (a) what the sources collectively say; " +
      "(b) where they differ and why it matters; (c) what this tells your reader.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    // The worked example is lifted into its own panel, carrying the cued quote (not some other span)…
    expect(container.querySelector("aside")?.textContent).toContain(
      "Source A claims that transit reduces congestion.",
    );
    // …AND the trailing enumeration becomes an alpha-marked ordered list (not raw "(a)" text).
    const list = container.querySelector("ol");
    expect(list).toHaveAttribute("type", "a");
    expect(within(list as HTMLElement).getAllByRole("listitem")).toHaveLength(3);
    expect(container.textContent).not.toContain("(a)");
  });

  it("lifts a 'Worked Example' paragraph into a literal/improved box with its note", () => {
    // The shape already-built courses authored as flat prose: a label, a literal phrasing, an
    // improved rewrite, and a parenthetical why. It must upgrade into the shared WorkedExample panel.
    const prose =
      "Worked Example 1: Literal: 'We will work very hard on this problem.' " +
      "With collocation: 'We will do the heavy lifting on this problem.' " +
      "(The collocation 'do the heavy lifting' means to undertake the most difficult work, " +
      "and suits a professional tone.)";

    const { container } = render(<Markdown>{prose}</Markdown>);

    // Both labelled sides are present…
    expect(within(container).getByText("Literal")).toBeInTheDocument();
    expect(within(container).getByText("With collocation")).toBeInTheDocument();
    expect(container.textContent).toContain("We will work very hard on this problem.");
    expect(container.textContent).toContain("We will do the heavy lifting on this problem.");
    // …the why note rides along…
    expect(container.textContent).toMatch(/suits a professional tone/);
    // …and the raw "Worked Example 1:" lead-in is gone (it was lifted, not left as flat prose).
    expect(container.textContent).not.toContain("Worked Example 1:");
  });

  it("lifts a 'Worked Example' with curly quotes and no note", () => {
    const prose =
      "Worked Example 2: Vague: “The thing is bad.” Precise: “Transit cuts commute time by 30%.”";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(within(container).getByText("Vague")).toBeInTheDocument();
    expect(within(container).getByText("Precise")).toBeInTheDocument();
    expect(container.textContent).toContain("Transit cuts commute time by 30%.");
    // No parenthetical → no "Why" note row.
    expect(within(container).queryByText("Why")).not.toBeInTheDocument();
  });

  it("does not lift a malformed 'Worked Example' that lacks a second labelled side", () => {
    // Only one labelled quote — not a literal-vs-improved contrast, so it is left as ordinary prose
    // (the example-panel splitter may still quote it, but it is never a worked-example panel).
    const prose = "Worked Example: Note that you might write: 'Keep it short and concrete.'";

    const { container } = render(<Markdown>{prose}</Markdown>);

    // No two-sided worked-example box — the improved-side label is absent.
    expect(within(container).queryByText("Why")).not.toBeInTheDocument();
    expect(container.textContent).toContain("Keep it short and concrete.");
  });

  it("leaves an ordinary paragraph (no enumeration) untouched", () => {
    const prose = "A sentence with one independent clause (and an aside) cannot express much.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelector("p")?.textContent).toBe(prose);
  });

  it("renders a sequential 'Step N:' run as an interactive stepper headed by each step", () => {
    const prose =
      "Step 1: Specialized vocabulary. Generalist dictionaries list one definition per word.\n\n" +
      "Step 2: Strategic subordination. A sentence with one clause cannot express complex reasoning.\n\n" +
      "Step 3: Calibrate register. Match word choice to your audience.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const stepper = container.querySelector('ol[aria-label="Steps"]');
    expect(stepper).not.toBeNull();
    const steps = within(stepper as HTMLElement).getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Step 1: Specialized vocabulary");
    expect(steps[0]).toHaveTextContent("Generalist dictionaries list one definition per word.");
    // Each step's node is a mark-as-done toggle (interactive + progress).
    expect(
      within(steps[0]!).getByRole("button", { name: /mark step 1 done/i }),
    ).toBeInTheDocument();
  });

  it("falls back to collapsible panels for a non-sequential labelled run", () => {
    // Numbers 1 then 3 (not 1..N) → not a step procedure, so collapsible sections instead.
    const prose = "Principle 1: Clarity. Say what you mean.\n\nPrinciple 3: Brevity. Then stop.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(container.querySelector('ol[aria-label="Steps"]')).toBeNull();
    expect(container.querySelectorAll("details")).toHaveLength(2);
  });

  it("does not sectionize a lone labelled paragraph (needs a real section run)", () => {
    const prose = "Step 1: Do the thing. Then keep reading as normal prose without a second step.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    expect(container.querySelector("details")).toBeNull();
    expect(container.querySelector('ol[aria-label="Steps"]')).toBeNull();
    expect(container.querySelector("p")?.textContent).toContain("Step 1: Do the thing.");
  });

  it("splits an enumeration that lives inside a step's body", () => {
    const prose =
      "Step 1: Specialized vocabulary. To upgrade: (1) read articles; (2) note recurring terms.\n\n" +
      "Step 2: Strategic subordination. Use subordinate clauses to show logic.";

    const { container } = render(<Markdown>{prose}</Markdown>);

    const stepper = container.querySelector('ol[aria-label="Steps"]');
    expect(stepper).not.toBeNull();
    const firstStep = within(stepper as HTMLElement).getAllByRole("listitem")[0]!;
    // The step body is collapsed by default, so query its (hidden) enumeration list.
    const list = within(firstStep).getByRole("list", { hidden: true });
    expect(within(list).getAllByRole("listitem", { hidden: true })).toHaveLength(2);
  });
});
