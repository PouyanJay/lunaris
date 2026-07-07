import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ViewToggle } from "./ViewToggle";

describe("ViewToggle", () => {
  it("marks the active view and leaves the other unchecked", () => {
    // Arrange / Act
    render(<ViewToggle value="lessons" onChange={() => {}} />);

    // Assert
    expect(screen.getByRole("radio", { name: /lessons/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /map/i })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /build/i })).not.toBeChecked();
  });

  it("selects a view when its option is clicked", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="lessons" onChange={onChange} />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));

    // Assert
    expect(onChange).toHaveBeenCalledWith("map");
  });

  it("advances with ArrowRight and moves focus to the new option", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="lessons" onChange={onChange} />);
    const lessons = screen.getByRole("radio", { name: /lessons/i });
    lessons.focus();

    // Act
    fireEvent.keyDown(lessons, { key: "ArrowRight" });

    // Assert — selection reported and focus followed.
    expect(onChange).toHaveBeenCalledWith("map");
    expect(screen.getByRole("radio", { name: /map/i })).toHaveFocus();
  });

  it("steps back with ArrowLeft and moves focus to the new option", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="map" onChange={onChange} />);
    const map = screen.getByRole("radio", { name: /map/i });
    map.focus();

    // Act
    fireEvent.keyDown(map, { key: "ArrowLeft" });

    // Assert
    expect(onChange).toHaveBeenCalledWith("lessons");
    expect(screen.getByRole("radio", { name: /lessons/i })).toHaveFocus();
  });

  it("wraps backward from the first option (Overview) to the last (Corpus)", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="overview" onChange={onChange} />);
    const overview = screen.getByRole("radio", { name: /overview/i });
    overview.focus();

    // Act
    fireEvent.keyDown(overview, { key: "ArrowLeft" });

    // Assert
    expect(onChange).toHaveBeenCalledWith("corpus");
  });

  it("wraps forward from the last option (Corpus) to the first (Overview)", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="corpus" onChange={onChange} />);
    const corpus = screen.getByRole("radio", { name: /corpus/i });
    corpus.focus();

    // Act
    fireEvent.keyDown(corpus, { key: "ArrowRight" });

    // Assert
    expect(onChange).toHaveBeenCalledWith("overview");
  });

  it("registers the Build view as an option", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="lessons" onChange={onChange} />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /build/i }));

    // Assert
    expect(onChange).toHaveBeenCalledWith("build");
  });

  it("registers the Corpus view as an option", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="lessons" onChange={onChange} />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /corpus/i }));

    // Assert
    expect(onChange).toHaveBeenCalledWith("corpus");
  });

  it("keeps only the active option in the tab order (roving tabindex)", () => {
    // Arrange / Act
    render(<ViewToggle value="map" onChange={() => {}} />);

    // Assert
    expect(screen.getByRole("radio", { name: /map/i })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: /lessons/i })).toHaveAttribute("tabindex", "-1");
  });
});
