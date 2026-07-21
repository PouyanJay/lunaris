import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** Variant coverage for the prose-formatting rules: each rule's trigger shapes fire, adversarial
 *  near-misses do not, and the rules generalise across subjects (not just the biology fixture). */

const hasHeading = () => screen.queryByRole("heading") !== null;
const hasChip = (c: HTMLElement) => c.querySelector('[data-category="data"]') !== null;
const hasFlow = () => screen.queryByRole("list", { name: /step chain/i }) !== null;

describe("prose formatting — variant coverage", () => {
  describe("R1 section labels — fires", () => {
    it.each([
      "STRATEGY: do the thing here now.",
      "UPSTREAM LAYER (alarmins): the cells respond.",
      "CANONICAL CYTOKINES: three of them exist.",
      "END STATE ANALYSIS: the system settles.",
    ])("lifts %j", (prose) => {
      render(<Markdown>{prose}</Markdown>);
      expect(hasHeading()).toBe(true);
    });
  });

  describe("R1 section labels — does not fire", () => {
    it.each([
      "The T2 axis produces three cytokines that drive disease.",
      "A: this single capital is not a label at all.",
      "NOTE: this is a callout, not a section label.",
      "It costs 5: that colon is not a label boundary.",
      "ALPHA BETA GAMMA DELTA EPSILON: five words exceed the label bound.",
    ])("leaves %j", (prose) => {
      render(<Markdown>{prose}</Markdown>);
      expect(hasHeading()).toBe(false);
    });
  });

  describe("R2 data tokens — fires / does not", () => {
    it.each(["IL-4", "Th2", "ILC2", "TSLP", "IgE", "600-eosinophil", "CO2"])(
      "chips %j",
      (token) => {
        const { container } = render(<Markdown>{`The marker ${token} appears in the sample here.`}</Markdown>);
        expect(hasChip(container)).toBe(true);
      },
    );
    it.each(["the year 2024 arrived", "a type 2 response here", "this is REALLY important now", "plain words only here"])(
      "leaves %j unchipped",
      (prose) => {
        const { container } = render(<Markdown>{prose}</Markdown>);
        expect(hasChip(container)).toBe(false);
      },
    );
  });

  describe("R3 arrow flow — fires only at >=2 arrows", () => {
    it("fires on 3 nodes", () => {
      render(<Markdown>{"The sequence is a → b → c to the finish."}</Markdown>);
      expect(hasFlow()).toBe(true);
    });
    it("does not fire on a single arrow", () => {
      render(<Markdown>{"It goes a → b and then it is done."}</Markdown>);
      expect(hasFlow()).toBe(false);
    });
  });

  describe("R4 series — fires / does not", () => {
    it("lifts a cue-introduced short series", () => {
      const { container } = render(
        <Markdown>{"It comes in three colors: red, green, and blue."}</Markdown>,
      );
      expect(container.querySelector("ul")).not.toBeNull();
    });
    it("leaves a long prose clause after a colon inline", () => {
      const { container } = render(
        <Markdown>{"The reason is this: the system depends on many slow feedback loops, which stabilize it over years."}</Markdown>,
      );
      expect(container.querySelector("ul")).toBeNull();
    });
    it("leaves a cueless series with a trailing clause inline (ambiguous to bound)", () => {
      const { container } = render(<Markdown>{"The parts are red, green, and blue in order."}</Markdown>);
      expect(container.querySelector("ul")).toBeNull();
    });
    it("does not lift a 2-item cued series (below the 3-item threshold)", () => {
      const { container } = render(<Markdown>{"It comes in two colors: red, and blue."}</Markdown>);
      expect(container.querySelector("ul")).toBeNull();
    });
  });

  describe("R5 emphasis — fires / does not", () => {
    it("bolds a definitional subject", () => {
      render(<Markdown>{"Recursion is the defining technique of the algorithm."}</Markdown>);
      expect(screen.getByText("Recursion").tagName).toBe("STRONG");
    });
    it("leaves an ordinary predicate unbolded", () => {
      const { container } = render(<Markdown>{"The function is a helper used across modules."}</Markdown>);
      expect(container.querySelector("strong")).toBeNull();
    });
  });

  describe("generalises across subjects (not just biology)", () => {
    it("formats a computer-science lesson", () => {
      const { container } = render(
        <Markdown>
          {"COMPILATION PIPELINE: source flows through the toolchain. The pipeline is lexer → parser → optimizer → codegen at the end."}
        </Markdown>,
      );
      expect(screen.getByRole("heading", { name: /compilation pipeline/i })).toBeInTheDocument();
      expect(hasFlow()).toBe(true);
      expect(hasChip(container)).toBe(false); // no data-shaped tokens here — nothing forced
    });

    it("formats a history lesson with a labelled series", () => {
      const { container } = render(
        <Markdown>
          {"CAUSES: several forces converged before 1914. Three drivers stand out: alliances, nationalism, and militarism."}
        </Markdown>,
      );
      expect(screen.getByRole("heading", { name: /causes/i })).toBeInTheDocument();
      const items = container.querySelectorAll("ul li");
      expect(Array.from(items).map((li) => li.textContent)).toEqual([
        "alliances",
        "nationalism",
        "militarism",
      ]);
    });
  });
});
