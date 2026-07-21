import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ASTHMA_PROSE } from "./lessonProse.fixture";
import { Markdown } from "./Markdown";

/** R8 — the meta-rules the whole formatting layer must uphold: it changes presentation, never wording;
 *  it is deterministic; it never lets unsafe markup through; and it composes with the existing lifts. */

/** Alphanumeric word tokens, keeping hyphenated ids ("il-4", "t2-high", "600-eosinophil") whole. */
const words = (text: string): string[] => text.toLowerCase().match(/[a-z0-9]+(?:-[a-z0-9]+)*/g) ?? [];

describe("prose formatting — guardrails (R8)", () => {
  it("adds no words and drops only list conjunctions (presentation-only)", () => {
    const { container } = render(<Markdown>{ASTHMA_PROSE}</Markdown>);
    const original = new Set(words(ASTHMA_PROSE));
    const rendered = words(container.textContent ?? "");
    const renderedSet = new Set(rendered);

    // No word is invented. A token missing from the original is only allowed if it is two original
    // words glued at an element boundary (e.g. a keyed row's "IL-4" + "drives" → "il-4drives" in
    // textContent — real browsers space these on copy / for screen readers); never new content.
    const isGlueOfTwoOriginals = (word: string): boolean => {
      for (let i = 1; i < word.length; i += 1) {
        if (original.has(word.slice(0, i)) && original.has(word.slice(i))) return true;
      }
      return false;
    };
    const invented = rendered.filter((word) => !original.has(word) && !isGlueOfTwoOriginals(word));
    expect(invented).toEqual([]);
    // The only words that may disappear are the "and"/"or" consumed when a series becomes a list.
    const dropped = [...original].filter((word) => !renderedSet.has(word));
    expect(dropped.every((word) => word === "and" || word === "or")).toBe(true);
  });

  it("is deterministic — the same prose renders identical markup twice", () => {
    const first = render(<Markdown>{ASTHMA_PROSE}</Markdown>).container.innerHTML;
    const second = render(<Markdown>{ASTHMA_PROSE}</Markdown>).container.innerHTML;
    expect(first).toBe(second);
  });

  it("keeps the sanitiser gate closed with the added custom elements", () => {
    const { container } = render(
      <Markdown>{"Stay safe <script>alert(1)</script> and [click](javascript:alert(2))."}</Markdown>,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("applies section-label and flow formatting to clean prose", () => {
    render(<Markdown>{"STRATEGY: follow the sequence a → b → c to the end here."}</Markdown>);
    expect(screen.getByRole("heading", { name: /strategy/i })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /step chain/i })).toBeInTheDocument();
  });

  it("does not regress the existing numbered-step lift", () => {
    render(
      <Markdown>
        {"STRATEGY: here is the plan. Step 1: warm up the model. Step 2: measure the latency."}
      </Markdown>,
    );
    // The section label still lifts…
    expect(screen.getByRole("heading", { name: /strategy/i })).toBeInTheDocument();
    // …and the proseStructure stepper still renders both steps.
    expect(screen.getByText(/warm up the model/)).toBeInTheDocument();
    expect(screen.getByText(/measure the latency/)).toBeInTheDocument();
  });

  it("composes every rule on the full reference prose", () => {
    const { container } = render(<Markdown>{ASTHMA_PROSE}</Markdown>);

    // R1: seven section heads.
    expect(screen.getAllByRole("heading")).toHaveLength(7);
    // R2: data-token chips present.
    expect(container.querySelectorAll('[data-category="data"]').length).toBeGreaterThan(5);
    // R3: the worked-example flow.
    const flow = screen.getByRole("list", { name: /step chain/i });
    expect(within(flow).getAllByRole("listitem")).toHaveLength(7);
    // R4a: at least one bullet list, R4b: the attribution keyed list.
    expect(container.querySelector("ul")).not.toBeNull();
    expect(screen.getAllByRole("term").length).toBeGreaterThanOrEqual(3);
    // R5: the definitional subject is bolded.
    expect(screen.getByText("Airway inflammation").tagName).toBe("STRONG");
    // R7: the worked-example and attribution sections are panelled.
    expect(container.querySelectorAll("section").length).toBeGreaterThanOrEqual(2);
  });
});
