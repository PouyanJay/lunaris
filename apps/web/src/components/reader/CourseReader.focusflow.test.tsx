import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Visual } from "../../types/course";
import { makeCourse, makeLesson, makeModule, routedFetch } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Walk the Learn mode forward: N clicks of the current advance button. */
function clickContinue(times: number) {
  for (let i = 0; i < times; i += 1) {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  }
}

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
    expect(within(map).getByRole("button", { name: /what this lesson expects/i })).toHaveAttribute(
      "aria-current",
      "step",
    );
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

  it("renders the resources step through LessonResources", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);

    // Act — step 4 is the demonstrate phase's resources.
    clickContinue(3);

    // Assert
    expect(screen.getByText("Binary search visualised")).toBeInTheDocument();
  });

  it("renders the self-check step through LessonScaffold", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);

    // Act — step 7 is the closing self-check item.
    clickContinue(6);

    // Assert
    expect(screen.getByText(/locate 7 in a 9-element sorted array/i)).toBeInTheDocument();
  });

  it("renders the assessment step through LessonAssessment", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);

    // Act — step 8, the module assessment finale.
    clickContinue(7);

    // Assert
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
    clickContinue(6);
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

  it("steps with the arrow keys inside the step surface", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const stage = screen.getByRole("region", { name: /lesson steps/i });

    // Act / Assert — right advances, left returns, left at the start stays put.
    fireEvent.keyDown(stage, { key: "ArrowRight" });
    expect(screen.getByText(/step 2 of 8/i)).toBeInTheDocument();
    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    expect(screen.getByText(/step 1 of 8/i)).toBeInTheDocument();
    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    expect(screen.getByText(/step 1 of 8/i)).toBeInTheDocument();
  });

  it("moves focus to the new step's card so the change is announced", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Assert
    expect(screen.getByRole("group", { name: "Step content" })).toHaveFocus();
  });

  it("offers the Read fallback for a lesson with nothing to step through", () => {
    // Arrange — an entirely empty lesson.
    const empty = { prose: "", visuals: [], claims: [], resources: [] };
    const course = makeCourse({
      modules: [
        makeModule({
          lessons: [
            makeLesson({
              segments: { activate: empty, demonstrate: empty, apply: empty, integrate: empty },
              expects: [],
              selfCheck: [],
            }),
          ],
        }),
      ],
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert — an honest empty state, not a blank stage or a phantom step counter.
    expect(screen.getByRole("status")).toHaveTextContent(/switch to read/i);
    expect(screen.queryByText(/step 1 of/i)).not.toBeInTheDocument();
  });

  it("renders a visual step through the branded renderer", () => {
    // Arrange — a demonstrate-phase flow visual becomes its own step (4 of 9 in this arc).
    const base = makeLesson();
    const visual: Visual = {
      kind: "spec",
      source: "",
      rendered: null,
      spec: {
        type: "flow",
        title: null,
        nodes: [{ id: "a", label: "Halve the range" }],
        edges: [],
      },
      mayerChecks: { coherence: true, signaling: true, spatialContiguity: true, redundancy: true },
    };
    const course = makeCourse();
    course.modules[0]!.lessons = [
      {
        ...base,
        segments: {
          ...base.segments,
          demonstrate: { ...base.segments.demonstrate, visuals: [visual] },
        },
      },
    ];
    render(<CourseReader course={course} />);

    // Act — intro → warm-up → demonstrate content → visual step.
    clickContinue(3);

    // Assert
    expect(screen.getByText("Halve the range")).toBeInTheDocument();
  });

  it("returns to step one when the focused lesson changes", () => {
    // Arrange — two lessons; walk into lesson 1.
    const course = makeCourse();
    course.modules[0]!.lessons = [makeLesson(), makeLesson({ id: "m-binary_search-l1" })];
    render(<CourseReader course={course} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText(/step 2 of/i)).toBeInTheDocument();

    // Act — jump to lesson 2 via the course outline.
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 2/i }));

    // Assert
    expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
  });

  it("persists the chosen mode for the next visit", () => {
    // Arrange — a stored Read preference wins on mount.
    localStorage.setItem(READER_MODE_KEY, "read");
    const { unmount } = render(<CourseReader course={makeCourse()} />);
    expect(screen.getByRole("heading", { name: "Warm-up" })).toBeInTheDocument();

    // Act — choose Learn; the preference is written back.
    fireEvent.click(screen.getByRole("radio", { name: "Learn" }));
    expect(localStorage.getItem(READER_MODE_KEY)).toBe("learn");
    unmount();

    // Assert — a fresh reader honours it.
    render(<CourseReader course={makeCourse()} />);
    expect(screen.getByRole("region", { name: /lesson steps/i })).toBeInTheDocument();
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
