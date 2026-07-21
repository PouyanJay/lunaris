import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** R4 — lift an inline series into a list: a "cue: a, b, and c" run becomes a bullet list, and a run
 *  of token-led sentences ("IL-4 drives…") becomes a keyed definition list. Conservative: it needs a
 *  terminal and/or connector and short items, so prose clauses and dash-appositives stay inline. */
describe("inline series → bullet list (R4a)", () => {
  it("lifts an em-dash series, keeping the lead-in as prose", () => {
    render(<Markdown>{"The Th2/ILC2 axis produces three core T2 cytokines—IL-4, IL-5, and IL-13."}</Markdown>);

    const list = screen.getByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["IL-4", "IL-5", "IL-13"]);
    // Lead-in survives as prose above the list (its "T2" token is chipped, so match a plain run).
    expect(screen.getByText(/produces three core/)).toBeInTheDocument();
    // items chip via R2.
    expect(within(list).getByText("IL-5")).toHaveAttribute("data-category", "data");
  });

  it("lifts a colon series embedded mid-paragraph, preserving the trailing sentence", () => {
    render(
      <Markdown>
        {"It drives the canonical features: airflow limitation, mucus plugging, airway remodeling, and hyperresponsiveness. The paradigm is established."}
      </Markdown>,
    );

    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "airflow limitation",
      "mucus plugging",
      "airway remodeling",
      "hyperresponsiveness",
    ]);
    expect(screen.getByText(/The paradigm is established\./)).toBeInTheDocument();
  });

  describe("does NOT fire", () => {
    it("leaves a dash appositive with no and/or connector inline", () => {
      const { container } = render(
        <Markdown>{"Diverse triggers—infectious, allergic, irritant, osmotic—activate the response."}</Markdown>,
      );
      expect(container.querySelector("ul")).toBeNull();
    });

    it("leaves a colon followed by a long prose clause inline", () => {
      const { container } = render(
        <Markdown>
          {"These are upstream drivers: they activate innate lymphoid cells and prime dendritic cells, which recruit and activate Th2 cells."}
        </Markdown>,
      );
      expect(container.querySelector("ul")).toBeNull();
    });
  });
});

describe("token-led sentences → keyed list (R4b)", () => {
  it("builds a definition list keyed by the leading token", () => {
    render(
      <Markdown>
        {"IL-4 drives Th2 differentiation. IL-5 recruits eosinophils to the airway. IL-13 drives mucus hypersecretion."}
      </Markdown>,
    );

    const terms = screen.getAllByRole("term");
    expect(terms.map((t) => t.textContent)).toEqual(["IL-4", "IL-5", "IL-13"]);
    expect(terms[0]!.closest("dl")).not.toBeNull();
    const defs = screen.getAllByRole("definition");
    expect(defs[0]!.textContent).toMatch(/drives Th2 differentiation/);
    expect(defs[1]!.textContent).toMatch(/recruits eosinophils to the airway/);
  });

  it("does not build a keyed list when sentences aren't all token-led", () => {
    const { container } = render(
      <Markdown>{"IL-4 drives differentiation. The response then escalates over time."}</Markdown>,
    );
    expect(container.querySelector("dl")).toBeNull();
  });

  it("does not mistake all-caps emphasis prose for a keyed list", () => {
    // NEVER/ALWAYS/ONLY read as emphasis, not tokens — a "guidelines" paragraph must stay prose.
    const { container } = render(
      <Markdown>{"NEVER skip the warmup. ALWAYS stretch first. ONLY then begin the set."}</Markdown>,
    );
    expect(container.querySelector("dl")).toBeNull();
  });
});
