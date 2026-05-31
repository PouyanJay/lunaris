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

  it("offers a lesson drill-in for a concept a module teaches", () => {
    // Arrange — binary_search is covered by the Binary Search module.
    const onOpenLesson = vi.fn();
    render(
      <KcDetailPanel
        course={makeCourse()}
        selectedId="binary_search"
        onClose={() => {}}
        onOpenLesson={onOpenLesson}
      />,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /open lesson/i }));

    // Assert — the drill-in carries the concept id.
    expect(onOpenLesson).toHaveBeenCalledWith("binary_search");
  });

  it("offers no drill-in for a concept no module teaches", () => {
    // Arrange / Act — comparison is not in any module's kcs.
    render(
      <KcDetailPanel
        course={makeCourse()}
        selectedId="comparison"
        onClose={() => {}}
        onOpenLesson={() => {}}
      />,
    );

    // Assert
    expect(screen.queryByRole("button", { name: /open lesson/i })).not.toBeInTheDocument();
  });

  it("offers no drill-in when no handler is supplied", () => {
    // Arrange / Act — binary_search is taught, but the caller wires no drill-in handler.
    render(<KcDetailPanel course={makeCourse()} selectedId="binary_search" onClose={() => {}} />);

    // Assert
    expect(screen.queryByRole("button", { name: /open lesson/i })).not.toBeInTheDocument();
  });
});
