import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Lesson } from "../../types/course";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

/** A lesson identifiable in the reader by its activate-phase prose — enough for navigation asserts. */
function lessonWith(id: string, activateProse: string): Lesson {
  const base = makeLesson({ id });
  return {
    ...base,
    segments: { ...base.segments, activate: { prose: activateProse, visuals: [], claims: [] } },
  };
}

/** Two modules, three lessons total — enough to exercise outline grouping and Prev/Next bounds. */
function multiLessonCourse() {
  return makeCourse({
    modules: [
      makeModule({
        id: "m1",
        title: "Foundations",
        lessons: [
          lessonWith("l1", "Prose for lesson one."),
          lessonWith("l2", "Prose for lesson two."),
        ],
      }),
      makeModule({ id: "m2", title: "Search", lessons: [lessonWith("l3", "Prose for lesson three.")] }),
    ],
  });
}

describe("CourseReader", () => {
  it("lists every module and lesson in the course outline", () => {
    // Arrange / Act
    render(<CourseReader course={multiLessonCourse()} />);

    // Assert — the outline groups lessons under their module titles.
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    expect(within(outline).getByText("Foundations")).toBeInTheDocument();
    expect(within(outline).getByText("Search")).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /lesson 1/i })).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /lesson 2/i })).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /lesson 3/i })).toBeInTheDocument();
  });

  it("focuses the first lesson by default and shows its position", () => {
    // Arrange / Act
    render(<CourseReader course={multiLessonCourse()} />);

    // Assert — lesson one is in focus, marked current in the outline, with a position indicator.
    expect(screen.getByText("Prose for lesson one.")).toBeInTheDocument();
    expect(screen.getByText(/lesson 1 of 3/i)).toBeInTheDocument();
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    expect(within(outline).getByRole("button", { name: /lesson 1/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("jumps to a lesson when its outline entry is clicked", () => {
    // Arrange
    render(<CourseReader course={multiLessonCourse()} />);
    const outline = screen.getByRole("navigation", { name: /course outline/i });

    // Act
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 3/i }));

    // Assert
    expect(screen.getByText("Prose for lesson three.")).toBeInTheDocument();
    expect(screen.queryByText("Prose for lesson one.")).not.toBeInTheDocument();
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
  });

  it("steps forward with Next and disables it on the last lesson", () => {
    // Arrange
    render(<CourseReader course={multiLessonCourse()} />);
    const next = screen.getByRole("button", { name: /next lesson/i });

    // Act — advance through every lesson.
    fireEvent.click(next);
    expect(screen.getByText("Prose for lesson two.")).toBeInTheDocument();
    fireEvent.click(next);

    // Assert — the last lesson is focused and Next is disabled.
    expect(screen.getByText("Prose for lesson three.")).toBeInTheDocument();
    expect(next).toBeDisabled();
  });

  it("steps back with Previous and disables it on the first lesson", () => {
    // Arrange — start on the last lesson.
    render(<CourseReader course={multiLessonCourse()} />);
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 3/i }));
    const prev = screen.getByRole("button", { name: /previous lesson/i });

    // Act — step back one lesson.
    fireEvent.click(prev);
    expect(screen.getByText("Prose for lesson two.")).toBeInTheDocument();

    // Act / Assert — stepping back to the first lesson disables Previous.
    fireEvent.click(prev);
    expect(screen.getByText("Prose for lesson one.")).toBeInTheDocument();
    expect(prev).toBeDisabled();
  });

  it("renders an empty state when no lessons are authored", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse({ modules: [] })} />);

    // Assert
    expect(screen.getByRole("status")).toHaveTextContent(/no lessons/i);
  });
});
