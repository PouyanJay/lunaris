import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

afterEach(() => {
  localStorage.clear();
});

// The course outline nests the focused lesson's sections (its arc: expects, phases, self-check,
// assessment) as navigable entries. With Read retired, the section level is driven by — and jumps
// within — the Learn (Focus Flow) step surface, which is the default offline.
describe("CourseReader — outline section nesting", () => {
  it("lists the focused lesson's sections under it in the course outline", () => {
    // Arrange / Act — the default fixture has expects + selfCheck + a module assessment.
    render(<CourseReader course={makeCourse()} />);

    // Assert — the outline nests the lesson's arc as navigable entries.
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    expect(within(outline).getByRole("button", { name: /warm-up/i })).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /practice/i })).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /self-check/i })).toBeInTheDocument();
    expect(
      within(outline).getByRole("button", { name: /check your understanding/i }),
    ).toBeInTheDocument();
  });

  it("jumps the Learn step surface to a section chosen from the outline", () => {
    // Arrange — the default lesson's Practice (apply) phase carries a recognisable line. (The
    // matcher skirts the auto-glossary-marked "binary search" term, which splits the text node.)
    render(<CourseReader course={makeCourse()} />);
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    expect(screen.queryByText(/searching for 7/i)).not.toBeInTheDocument();

    // Act — pick the Practice section.
    fireEvent.click(within(outline).getByRole("button", { name: /practice/i }));

    // Assert — the guided step surface lands on that phase's content.
    expect(screen.getByText(/on \[1, 3, 5, 7, 9\] searching for 7/i)).toBeInTheDocument();
  });

  it("nests only the four phase sections for a bare-arc lesson", () => {
    // Arrange — a pre-P7.3 lesson: no expects, no selfCheck, and a module without assessment.
    const course = makeCourse({
      modules: [
        makeModule({
          lessons: [makeLesson({ expects: [], selfCheck: [] })],
        }),
      ],
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the section level holds exactly the phases; no bookend / assessment entries.
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    expect(within(outline).getByRole("button", { name: /warm-up/i })).toBeInTheDocument();
    expect(within(outline).queryByRole("button", { name: /self-check/i })).not.toBeInTheDocument();
    expect(
      within(outline).queryByRole("button", { name: /check your understanding/i }),
    ).not.toBeInTheDocument();
  });
});
