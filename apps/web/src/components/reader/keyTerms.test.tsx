import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** R5 — bold the subject of a definitional statement ("X is the hallmark …"). Deliberately rare: it
 *  fires only on a small set of definitional cue words, so ordinary "is a/the …" prose stays plain. */
describe("key-term emphasis (R5)", () => {
  it("bolds the subject of a 'is the hallmark …' statement, mid-paragraph", () => {
    render(
      <Markdown>
        {"The response begins early. Airway inflammation is the hallmark feature of asthma."}
      </Markdown>,
    );

    const strong = screen.getByText("Airway inflammation");
    expect(strong.tagName).toBe("STRONG");
    // Only the subject is bolded, not the whole sentence.
    expect(screen.getByText(/is the hallmark feature of asthma/)).toBeInTheDocument();
  });

  it("fires on 'are the dominant …' too", () => {
    render(<Markdown>{"Alarmins are the dominant upstream drivers of the cascade."}</Markdown>);
    expect(screen.getByText("Alarmins").tagName).toBe("STRONG");
  });

  describe("does NOT fire (conservative)", () => {
    it("leaves an ordinary 'is a/the …' sentence unbolded", () => {
      const { container } = render(<Markdown>{"The cell is a small unit of the body."}</Markdown>);
      expect(container.querySelector("strong")).toBeNull();
    });

    it("does not bold on a non-definitional cue like 'is the way'", () => {
      const { container } = render(<Markdown>{"This is the way the process runs."}</Markdown>);
      expect(container.querySelector("strong")).toBeNull();
    });

    it("still renders author markdown bold normally", () => {
      render(<Markdown>{"Keep it **safe** always."}</Markdown>);
      expect(screen.getByText("safe").tagName).toBe("STRONG");
    });
  });
});
