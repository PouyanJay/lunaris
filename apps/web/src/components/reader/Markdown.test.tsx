import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders bold and italic instead of literal asterisks", () => {
    const { container } = render(
      <Markdown>{"The strategy is *source with purpose* and **draft with anchors**."}</Markdown>,
    );

    // No raw markdown markers leak to the page.
    expect(container.textContent).not.toContain("*");
    expect(container.querySelector("em")?.textContent).toBe("source with purpose");
    expect(container.querySelector("strong")?.textContent).toBe("draft with anchors");
  });

  it("renders unordered and ordered lists", () => {
    render(<Markdown>{"Steps:\n\n- first item\n- second item\n\n1. one\n2. two"}</Markdown>);

    expect(screen.getByText("first item").tagName).toBe("LI");
    expect(screen.getByText("one").closest("ol")).not.toBeNull();
    expect(screen.getByText("first item").closest("ul")).not.toBeNull();
  });

  it("renders a link as a real new-tab anchor and strips raw HTML (sanitised)", () => {
    render(
      <Markdown>
        {"See [the guide](https://example.org/g). <script>alert(1)</script><b>raw</b>"}
      </Markdown>,
    );

    const link = screen.getByRole("link", { name: "the guide" });
    expect(link).toHaveAttribute("href", "https://example.org/g");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    // Raw HTML is sanitised away — no executable/raw markup survives.
    expect(document.querySelector("script")).toBeNull();
  });
});
