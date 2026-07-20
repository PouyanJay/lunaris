import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCourse } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

/** Field Guide (lesson-experience redesign phase 1): the reading-meta band. */
describe("CourseReader — reading meta band", () => {
  it("shows the band with an estimated reading time for the focused lesson", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse()} />);

    // Assert — the band is a labelled group carrying the mono reading-time metric.
    const band = screen.getByRole("group", { name: /reading progress/i });
    expect(band).toHaveTextContent(/min read/i);
  });
});
