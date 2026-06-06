import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArrayViz } from "./ArrayViz";
import { Markdown } from "./Markdown";

describe("ArrayViz", () => {
  it("renders each value over its 0-based index and inspects a cell on select", () => {
    render(<ArrayViz values="[240, 180, 195]" />);

    const cells = screen.getAllByRole("listitem");
    expect(cells).toHaveLength(3);
    // Index 0 holds the first value; the cell is labelled with both index and value.
    const first = within(cells[0]!).getByRole("button", { name: "Index 0, value 240" });

    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Index 0 → 240");
  });

  it("renders nothing for an empty list", () => {
    const { container } = render(<ArrayViz values="" />);
    expect(container.querySelector("figure")).toBeNull();
  });
});

describe("array visual in prose", () => {
  it("renders a ```array fence as the indexed array visual", () => {
    render(<Markdown>{"```array\n240, 180, 195, 210, 225\n```"}</Markdown>);

    expect(screen.getByRole("figure", { name: "Array" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Index 4, value 225" })).toBeInTheDocument();
  });

  it("auto-detects a standalone numeric array literal paragraph", () => {
    render(<Markdown>{"[240, 180, 195, 210, 225]"}</Markdown>);

    expect(screen.getByRole("figure", { name: "Array" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("leaves an array embedded in a sentence as prose", () => {
    const { container } = render(
      <Markdown>{"We store lengths in [240, 180, 195] for the demo."}</Markdown>,
    );

    expect(container.querySelector("figure")).toBeNull();
    expect(container.querySelector("p")?.textContent).toContain("[240, 180, 195]");
  });
});
