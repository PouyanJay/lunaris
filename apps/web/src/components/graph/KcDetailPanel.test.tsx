import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeCourse } from "../../test/fixtures";
import { KcDetailPanel } from "./KcDetailPanel";

describe("KcDetailPanel", () => {
  it("shows the concept, its prerequisites, covering module and source", () => {
    render(<KcDetailPanel course={makeCourse()} selectedId="binary_search" onClose={() => {}} />);

    expect(screen.getByRole("heading", { name: "Binary Search" })).toBeInTheDocument();
    // Prerequisite of binary_search is sorted_order.
    expect(screen.getByText("Sorted Order")).toBeInTheDocument();
    expect(screen.getByText("Prerequisites · 1")).toBeInTheDocument();
    // Covered by the Binary Search module; grounded by the CLRS citation.
    expect(screen.getByText("Covered by · 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CLRS" })).toHaveAttribute(
      "href",
      "https://example.org/clrs",
    );
  });

  it("calls a foundation concept out as having no prerequisites", () => {
    render(<KcDetailPanel course={makeCourse()} selectedId="comparison" onClose={() => {}} />);

    expect(screen.getByText("Prerequisites · 0")).toBeInTheDocument();
    expect(screen.getByText(/foundation concept/i)).toBeInTheDocument();
  });

  it("moves focus to the close button so keyboard users land in the panel", () => {
    render(<KcDetailPanel course={makeCourse()} selectedId="binary_search" onClose={() => {}} />);

    expect(screen.getByRole("button", { name: "Close details" })).toHaveFocus();
  });

  it("closes when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<KcDetailPanel course={makeCourse()} selectedId="binary_search" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close details" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<KcDetailPanel course={makeCourse()} selectedId="binary_search" onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when the selected concept is not in the graph", () => {
    const { container } = render(
      <KcDetailPanel course={makeCourse()} selectedId="ghost" onClose={() => {}} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
