import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

const INDEX = new Map([["recursion", "A function calling itself."]]);

describe("Markdown — glossary auto-marking", () => {
  it("marks the first plain-prose occurrence of an indexed term", () => {
    // Arrange / Act
    render(<Markdown glossary={INDEX}>Recursion is powerful. Recursion repeats.</Markdown>);

    // Assert — one hoverable term, not two; the rest of the prose is untouched.
    const terms = screen.getAllByRole("button", { name: "Recursion" });
    expect(terms).toHaveLength(1);
  });

  it("never marks terms inside code", () => {
    // Arrange / Act
    render(<Markdown glossary={INDEX}>{"Use `recursion` in code."}</Markdown>);

    // Assert
    expect(screen.queryByRole("button", { name: "recursion" })).not.toBeInTheDocument();
  });

  it("defers to an authored :term directive for the same term", () => {
    // Arrange / Act — the author already defined it; auto-marking must not double up.
    render(
      <Markdown glossary={INDEX}>
        {':term[recursion]{title="Authored."} And recursion again.'}
      </Markdown>,
    );

    // Assert — exactly the authored one.
    const term = screen.getByRole("button", { name: "recursion" });
    expect(term).toBeInTheDocument();
  });

  it("renders plain markdown untouched when no glossary is supplied", () => {
    // Arrange / Act
    render(<Markdown>Recursion is powerful.</Markdown>);

    // Assert
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
