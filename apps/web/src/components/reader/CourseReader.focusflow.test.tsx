import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCourse } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

/** Focus Flow (lesson-experience redesign phase 2): the guided Learn mode. */
describe("CourseReader — Learn mode", () => {
  it("opens in Learn mode by default with a step card and mode toggle", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse()} />);

    // Assert — the mode toggle is a radiogroup with Learn selected, and the guided step
    // surface is present instead of the long-form phases.
    const toggle = screen.getByRole("radiogroup", { name: /reading mode/i });
    expect(toggle).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Learn" })).toBeChecked();
    expect(screen.getByRole("region", { name: /lesson steps/i })).toBeInTheDocument();
    expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Warm-up" })).not.toBeInTheDocument();
  });

  it("switches to the long-form Read mode from the toggle", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: "Read" }));

    // Assert — the Field Guide page is back.
    expect(screen.getByRole("heading", { name: "Warm-up" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /lesson steps/i })).not.toBeInTheDocument();
  });
});
