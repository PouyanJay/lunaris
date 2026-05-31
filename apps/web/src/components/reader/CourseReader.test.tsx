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

/** One module, two lessons, with objectives (module-start) and an assessment (module-end). */
function moduleWithObjectivesAndAssessment() {
  return makeCourse({
    modules: [
      makeModule({
        id: "m1",
        title: "Foundations",
        objectives: [
          {
            statement: "Locate a target in a sorted array with binary search.",
            bloomLevel: "apply",
            kc: "binary_search",
            assessedBy: ["i1"],
          },
        ],
        lessons: [lessonWith("l1", "Lesson one prose."), lessonWith("l2", "Lesson two prose.")],
        assessment: {
          items: [
            {
              id: "i1",
              prompt: "What is the worst-case time complexity?",
              objective: "binary_search",
              answer: "O(log n)",
            },
          ],
        },
      }),
    ],
  });
}

describe("CourseReader — lesson body", () => {
  it("renders the four Merrill phases of the focused lesson", () => {
    // Arrange / Act
    render(<CourseReader course={moduleWithObjectivesAndAssessment()} />);

    // Assert
    expect(screen.getByRole("heading", { name: "Activate" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Demonstrate" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Apply" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Integrate" })).toBeInTheDocument();
  });

  it("shows the module's Bloom-tagged objectives on its first lesson only", () => {
    // Arrange / Act — the first lesson is focused by default.
    render(<CourseReader course={moduleWithObjectivesAndAssessment()} />);

    // Assert — objectives + Bloom level are present on the module's opening lesson.
    expect(screen.getByText(/learning objectives/i)).toBeInTheDocument();
    expect(screen.getByText("Locate a target in a sorted array with binary search.")).toBeInTheDocument();
    expect(screen.getByText("apply")).toBeInTheDocument();

    // Act — move off the first lesson; objectives no longer show.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));
    expect(screen.queryByText(/learning objectives/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText("Locate a target in a sorted array with binary search."),
    ).not.toBeInTheDocument();
  });

  it("shows the assessment on the module's last lesson, with answers revealable", () => {
    // Arrange
    render(<CourseReader course={moduleWithObjectivesAndAssessment()} />);

    // Assert — assessment is hidden on the first (non-final) lesson.
    expect(screen.queryByText("What is the worst-case time complexity?")).not.toBeInTheDocument();

    // Act — go to the last lesson.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));

    // Assert — the assessment prompt shows; the answer is hidden until revealed.
    expect(screen.getByText("What is the worst-case time complexity?")).toBeInTheDocument();
    expect(screen.queryByText("O(log n)")).not.toBeInTheDocument();

    // Act — reveal the answer.
    fireEvent.click(screen.getByRole("button", { name: /show answer/i }));
    expect(screen.getByText("O(log n)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide answer/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
