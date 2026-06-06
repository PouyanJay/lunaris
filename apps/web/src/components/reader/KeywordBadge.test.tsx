import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("keyword badges in prose", () => {
  it("renders an uppercase HTTP method as a category-toned badge", () => {
    const { container } = render(
      <Markdown>{"Use POST to submit data and DELETE to remove it."}</Markdown>,
    );

    // The badge is an inline chip carrying its category (the tone); the word stays the label.
    const post = screen.getByText("POST");
    expect(post).toHaveAttribute("data-category", "create");
    expect(screen.getByText("DELETE")).toHaveAttribute("data-category", "delete");
    // The surrounding prose is preserved around the badges.
    expect(container.textContent).toBe("Use POST to submit data and DELETE to remove it.");
  });

  it("does not badge the ordinary lowercase word 'delete' or a substring", () => {
    const { container } = render(
      <Markdown>{"You can delete the file; GETTING started is easy."}</Markdown>,
    );

    expect(container.querySelector("[data-category]")).toBeNull();
    expect(container.textContent).toContain("delete the file");
  });

  it("leaves HTTP methods inside a link as plain link text", () => {
    render(<Markdown>{"See [the POST docs](https://example.org/post)."}</Markdown>);

    const link = screen.getByRole("link", { name: "the POST docs" });
    expect(link.querySelector("[data-category]")).toBeNull();
  });
});
