import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ViewToggle } from "./ViewToggle";

describe("ViewToggle", () => {
  it("marks the active view and leaves the other unchecked", () => {
    // Arrange / Act
    render(<ViewToggle value="learn" onChange={() => {}} />);

    // Assert
    expect(screen.getByRole("radio", { name: /learn/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /map/i })).not.toBeChecked();
  });

  it("selects a view when its option is clicked", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="learn" onChange={onChange} />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));

    // Assert
    expect(onChange).toHaveBeenCalledWith("map");
  });

  it("advances with ArrowRight and moves focus to the new option", () => {
    // Arrange
    const onChange = vi.fn();
    render(<ViewToggle value="learn" onChange={onChange} />);
    const learn = screen.getByRole("radio", { name: /learn/i });
    learn.focus();

    // Act
    fireEvent.keyDown(learn, { key: "ArrowRight" });

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
    expect(onChange).toHaveBeenCalledWith("learn");
    expect(screen.getByRole("radio", { name: /learn/i })).toHaveFocus();
  });

  it("wraps around the ends", () => {
    // Arrange — on the first option, ArrowLeft should wrap to the last.
    const onChange = vi.fn();
    render(<ViewToggle value="learn" onChange={onChange} />);
    const learn = screen.getByRole("radio", { name: /learn/i });
    learn.focus();

    // Act
    fireEvent.keyDown(learn, { key: "ArrowLeft" });

    // Assert
    expect(onChange).toHaveBeenCalledWith("map");
  });

  it("keeps only the active option in the tab order (roving tabindex)", () => {
    // Arrange / Act
    render(<ViewToggle value="map" onChange={() => {}} />);

    // Assert
    expect(screen.getByRole("radio", { name: /map/i })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: /learn/i })).toHaveAttribute("tabindex", "-1");
  });
});
