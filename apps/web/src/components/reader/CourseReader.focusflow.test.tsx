import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeLesson, routedFetch } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it("walks the lesson one step at a time with Continue and Back", () => {
    // Arrange — the fixture lesson chunks into 8 steps (intro → 4 phase contents + resources →
    // check → assessment).
    render(<CourseReader course={makeCourse()} />);
    expect(screen.getByText(/step 1 of 8/i)).toBeInTheDocument();
    // The intro step: the expects bookend.
    expect(screen.getByText(/you can compare two numbers/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();

    // Act — advance.
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Assert — the Warm-up chunk is on screen, alone.
    expect(screen.getByText(/step 2 of 8/i)).toBeInTheDocument();
    expect(screen.getByText(/recall how you find a word/i)).toBeInTheDocument();
    expect(screen.queryByText(/you can compare two numbers/i)).not.toBeInTheDocument();

    // Act — and back again.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText(/step 1 of 8/i)).toBeInTheDocument();
  });

  it("shows the remaining reading time and the section map", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse()} />);

    // Assert — mono metrics + a map naming the arc's sections, with the current one marked.
    expect(screen.getByText(/min left/i)).toBeInTheDocument();
    const map = screen.getByRole("navigation", { name: /lesson sections/i });
    expect(within(map).getByRole("button", { name: /warm-up/i })).toBeInTheDocument();
    expect(
      within(map).getByRole("button", { name: /what this lesson expects/i }),
    ).toHaveAttribute("aria-current", "step");
  });

  it("jumps to a section's first step from the section map", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const map = screen.getByRole("navigation", { name: /lesson sections/i });

    // Act
    fireEvent.click(within(map).getByRole("button", { name: /practice/i }));

    // Assert — Practice is step 5 in the fixture arc. ("binary search" itself is glossary-
    // wrapped mid-sentence, so match a phrase that stays one text node.)
    expect(screen.getByText(/step 5 of 8/i)).toBeInTheDocument();
    expect(screen.getByText(/searching for 7/i)).toBeInTheDocument();
  });

  it("renders resource, check, and assessment steps with the house components", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const continueButton = () => screen.getByRole("button", { name: "Continue" });

    // Act / Assert — step 4 is the demonstrate phase's resources.
    fireEvent.click(continueButton());
    fireEvent.click(continueButton());
    fireEvent.click(continueButton());
    expect(screen.getByText("Binary search visualised")).toBeInTheDocument();

    // Steps 5–6 content; step 7 the self-check item.
    fireEvent.click(continueButton());
    fireEvent.click(continueButton());
    fireEvent.click(continueButton());
    expect(screen.getByText(/locate 7 in a 9-element sorted array/i)).toBeInTheDocument();

    // Step 8: the module assessment.
    fireEvent.click(continueButton());
    expect(screen.getByText(/worst-case time complexity/i)).toBeInTheDocument();
  });

  it("drives the outline's section entries from the step position", () => {
    // Arrange — jump to Practice via the section map.
    render(<CourseReader course={makeCourse()} />);
    const map = screen.getByRole("navigation", { name: /lesson sections/i });
    fireEvent.click(within(map).getByRole("button", { name: /practice/i }));

    // Assert — the course outline mirrors the step position, no scroll involved.
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    expect(within(outline).getByRole("button", { name: /practice/i })).toHaveAttribute(
      "aria-current",
      "location",
    );
    expect(within(outline).getByRole("button", { name: /warm-up/i })).toHaveAttribute(
      "data-state",
      "done",
    );
  });

  it("jumps to a section's first step from the course outline", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const outline = screen.getByRole("navigation", { name: "Course outline" });

    // Act
    fireEvent.click(within(outline).getByRole("button", { name: /self-check/i }));

    // Assert — the self-check is step 7 in the fixture arc.
    expect(screen.getByText(/step 7 of 8/i)).toBeInTheDocument();
  });

  it("marks the lesson done and advances when the final step's Continue is pressed", async () => {
    // Arrange — two lessons + a live progress store (routed fetch), so completion exercises the
    // real progress layer, not a mock of it.
    const fetchMock = routedFetch({
      progress: { courseId: "course-test", objectives: [], lessons: [] },
    });
    vi.stubGlobal("fetch", fetchMock);
    const course = makeCourse();
    course.modules[0]!.lessons = [makeLesson(), makeLesson({ id: "m-binary_search-l1" })];
    render(<CourseReader course={course} apiBaseUrl="http://api.test" />);
    // The first-open in_progress mark proves the progress snapshot has landed.
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes("/progress/lesson")),
      ).toBe(true);
    });

    // Act — lesson 1 (first in module, no assessment) is 7 steps; walk to the end and complete.
    for (let i = 0; i < 6; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Next lesson" }));

    // Assert — the done mark was PUT for lesson 1 and the reader advanced to lesson 2.
    await waitFor(() => {
      const doneCall = fetchMock.mock.calls.find(
        (call) =>
          String(call[0]).includes("/progress/lesson") &&
          String((call[1] as RequestInit | undefined)?.body ?? "").includes('"done"'),
      );
      expect(doneCall).toBeDefined();
    });
    expect(screen.getByText("Lesson 2 of 2")).toBeInTheDocument();
    expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
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
