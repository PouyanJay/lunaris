import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("inline highlight (==text==)", () => {
  it("renders ==text== as a <mark> highlight", () => {
    const { container } = render(<Markdown>{"Always ==back up== before you start."}</Markdown>);

    const mark = container.querySelector("mark");
    expect(mark).not.toBeNull();
    expect(mark).toHaveTextContent("back up");
    expect(container.textContent).toBe("Always back up before you start.");
  });

  it("leaves text without == markers unchanged", () => {
    const { container } = render(<Markdown>{"Nothing to highlight here at all."}</Markdown>);
    expect(container.querySelector("mark")).toBeNull();
  });
});

describe("symbol tags (/x/)", () => {
  it("tags phonetic slash notation as a symbol chip", () => {
    render(<Markdown>{"The sounds /p/, /l/, and /ʃ/ are all clearly present."}</Markdown>);

    const p = screen.getByText("/p/");
    expect(p).toHaveAttribute("data-category", "symbol");
    expect(screen.getByText("/ʃ/")).toHaveAttribute("data-category", "symbol");
  });

  it("does not tag file paths or dates as symbols", () => {
    const { container } = render(
      <Markdown>{"See path/to/file and the date 12/25/2024 in context."}</Markdown>,
    );

    expect(container.querySelector('[data-category="symbol"]')).toBeNull();
    expect(container.textContent).toContain("path/to/file");
    expect(container.textContent).toContain("12/25/2024");
  });
});
