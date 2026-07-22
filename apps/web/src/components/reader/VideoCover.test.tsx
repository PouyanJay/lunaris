import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VideoCover } from "./VideoCover";

describe("VideoCover", () => {
  it("renders the title and meta eyebrow when given", () => {
    render(<VideoCover title="Logging in over plain HTTP" meta="6 chapters · 2:34" />);
    expect(screen.getByText("Logging in over plain HTTP")).toBeInTheDocument();
    expect(screen.getByText("6 chapters · 2:34")).toBeInTheDocument();
  });

  it("renders the meta eyebrow alone when no title is given", () => {
    const { container } = render(<VideoCover meta="Course trailer" />);
    expect(screen.getByText("Course trailer")).toBeInTheDocument();
    expect(container.querySelector("h3")).toBeNull();
  });

  it("renders a text-free (black) cover when no title/meta is given", () => {
    const { container } = render(<VideoCover />);
    expect(container.querySelector("h3")).toBeNull();
    expect(container.textContent).toBe("");
  });
});
