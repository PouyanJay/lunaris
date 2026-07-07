import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders its text with the quiet meta category by default", () => {
    render(<Badge>O(log n)</Badge>);
    expect(screen.getByText("O(log n)")).toHaveAttribute("data-category", "meta");
  });

  it("carries the requested category on the chip", () => {
    render(<Badge category="delete">DROP TABLE</Badge>);
    expect(screen.getByText("DROP TABLE")).toHaveAttribute("data-category", "delete");
  });

  it("forwards additional props and className", () => {
    render(
      <Badge className="extra" title="binary search">
        bsearch
      </Badge>,
    );
    const chip = screen.getByText("bsearch");
    expect(chip).toHaveClass("extra");
    expect(chip).toHaveAttribute("title", "binary search");
  });
});
