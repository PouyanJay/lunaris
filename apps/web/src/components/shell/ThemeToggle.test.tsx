import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  it("in light mode, offers to switch to dark and reads as not-pressed", () => {
    // Arrange / Act
    render(<ThemeToggle theme="light" onToggle={() => {}} />);

    // Assert
    const button = screen.getByRole("button", { name: /switch to dark mode/i });
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("in dark mode, offers to switch to light and reads as pressed", () => {
    // Arrange / Act
    render(<ThemeToggle theme="dark" onToggle={() => {}} />);

    // Assert
    const button = screen.getByRole("button", { name: /switch to light mode/i });
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("calls onToggle when clicked, in either mode", () => {
    // Arrange
    const onToggle = vi.fn();
    const { rerender } = render(<ThemeToggle theme="light" onToggle={onToggle} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /switch to dark mode/i }));
    rerender(<ThemeToggle theme="dark" onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("button", { name: /switch to light mode/i }));

    // Assert
    expect(onToggle).toHaveBeenCalledTimes(2);
  });
});
