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
    const originalSet = new Set(words(ASTHMA_PROSE));

    // Element boundaries glue two adjacent words in textContent (a keyed row's "IL-4" + "drives" →
    // "il-4drives"; real browsers space these on copy / for screen readers). Un-glue each rendered
    // token into its constituent original words so the count comparison below is faithful.
    const isGlueOfTwoOriginals = (word: string): string[] | null => {
      for (let i = 1; i < word.length; i += 1) {
        if (originalSet.has(word.slice(0, i)) && originalSet.has(word.slice(i))) {
          return [word.slice(0, i), word.slice(i)];
        }
      }
      return null;
    };
    const rendered = words(container.textContent ?? "").flatMap(
      (word) => isGlueOfTwoOriginals(word) ?? [word],
    );

    // No word is invented (nothing paraphrased or added).
    expect(rendered.filter((word) => !originalSet.has(word))).toEqual([]);

    // Multiset (occurrence-count) comparison — a Set would hide a single dropped instance of a word
    // that recurs elsewhere ("airway" appears 13×). Every word must survive with the SAME count,
    // except "and"/"or", which are consumed when an inline series becomes a list.
    const counts = (list: string[]): Map<string, number> => {
      const map = new Map<string, number>();
      for (const word of list) map.set(word, (map.get(word) ?? 0) + 1);
      return map;
    };
    const originalCounts = counts(words(ASTHMA_PROSE));
    const renderedCounts = counts(rendered);
    for (const [word, originalCount] of originalCounts) {
      const renderedCount = renderedCounts.get(word) ?? 0;
      if (word === "and" || word === "or") {
        expect(renderedCount).toBeLessThanOrEqual(originalCount);
      } else {
        expect(renderedCount, `count changed for "${word}"`).toBe(originalCount);
      }
    }
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
