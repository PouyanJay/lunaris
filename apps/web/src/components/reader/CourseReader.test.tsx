import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Claim, Lesson, Visual } from "../../types/course";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

const NO_MAYER = {
  coherence: false,
  signaling: false,
  spatialContiguity: false,
  redundancy: false,
};

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
      makeModule({
        id: "m2",
        title: "Search",
        lessons: [lessonWith("l3", "Prose for lesson three.")],
      }),
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

  it("regenerates the focused lesson and shows the updated content", async () => {
    // Arrange — a handler that returns a course with rewritten activate prose.
    const updated = makeCourse();
    updated.modules[0]!.lessons[0]!.segments.activate = {
      prose: "Regenerated prose.",
      visuals: [],
      claims: [],
    };
    const onRegenerate = vi.fn().mockResolvedValue(updated);
    const course = makeCourse();
    const originalProse = course.modules[0]!.lessons[0]!.segments.activate.prose;
    render(<CourseReader course={course} onRegenerate={onRegenerate} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));

    // Assert — the handler gets the focused lesson id, and the updated prose replaces the old.
    expect(onRegenerate).toHaveBeenCalledWith(course.modules[0]!.lessons[0]!.id);
    expect(await screen.findByText("Regenerated prose.")).toBeInTheDocument();
    expect(screen.queryByText(originalProse)).not.toBeInTheDocument();
  });

  it("hides the regenerate action when no handler is provided", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse()} />);

    // Assert
    expect(screen.queryByRole("button", { name: /regenerate/i })).not.toBeInTheDocument();
  });

  it("renders an empty state when no lessons are authored", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse({ modules: [] })} />);

    // Assert
    expect(screen.getByRole("status")).toHaveTextContent(/no lessons/i);
  });

  it("renders a segment's branded visual inside the reader", () => {
    // Arrange — a lesson whose demonstrate phase carries a flow-spec visual.
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
      mayerChecks: NO_MAYER,
    };
    const course = makeCourse({
      modules: [
        makeModule({
          lessons: [
            {
              ...base,
              segments: {
                ...base.segments,
                demonstrate: { prose: "Demo.", visuals: [visual], claims: [] },
              },
            },
          ],
        }),
      ],
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the branded renderer drew the spec's node.
    expect(screen.getByText("Halve the range")).toBeInTheDocument();
  });

  it("skips a module with no authored lessons in the outline", () => {
    // Arrange
    const course = makeCourse({
      modules: [
        makeModule({ id: "m-empty", title: "Empty", lessons: [] }),
        makeModule({ id: "m-real", title: "Real", lessons: [makeLesson()] }),
      ],
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    expect(within(outline).queryByText("Empty")).not.toBeInTheDocument();
    expect(within(outline).getByText("Real")).toBeInTheDocument();
  });

  it("focuses the lesson covering a concept on a focus request (Map drill-in)", () => {
    // Arrange — binary_search is taught by the second module (its lesson is Lesson 3).
    const course = makeCourse({
      modules: [
        makeModule({
          id: "m1",
          title: "Foundations",
          lessons: [lessonWith("l1", "Prose one."), lessonWith("l2", "Prose two.")],
        }),
        makeModule({
          id: "m2",
          title: "Search",
          kcs: ["binary_search"],
          lessons: [lessonWith("l3", "Prose three.")],
        }),
      ],
    });
    const { rerender } = render(<CourseReader course={course} />);
    expect(screen.getByText("Prose one.")).toBeInTheDocument();

    // Act — a drill-in request targeting binary_search.
    rerender(<CourseReader course={course} focusRequest={{ kc: "binary_search", seq: 1 }} />);

    // Assert — the reader jumps to that module's lesson.
    expect(screen.getByText("Prose three.")).toBeInTheDocument();
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
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

/** Single-lesson course whose demonstrate phase carries `claim`; default provenance includes src-1. */
function courseWithDemonstrateClaim(claim: Claim, provenance = makeCourse().provenance) {
  const base = makeLesson();
  return makeCourse({
    provenance,
    modules: [
      makeModule({
        lessons: [
          {
            ...base,
            segments: {
              ...base.segments,
              demonstrate: { prose: "Demonstration.", visuals: [], claims: [claim] },
            },
          },
        ],
      }),
    ],
  });
}

describe("CourseReader — claims & provenance", () => {
  it("renders a claim with its verification status and resolved source", () => {
    // Arrange — the default course's demonstrate phase has a supported claim citing src-1.
    const course = makeCourse();

    // Act
    render(<CourseReader course={course} />);

    // Assert — the claim, its status, and the resolved citation (a real outbound link) all show.
    expect(screen.getByText("Comparison reduces the problem size each step.")).toBeInTheDocument();
    expect(screen.getByText("SUPPORTED")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "CLRS" });
    expect(link).toHaveAttribute("href", "https://example.org/clrs");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("marks a claim whose citation cannot be resolved", () => {
    // Arrange — the supported claim still cites src-1, but provenance is empty so it won't resolve.
    const course = makeCourse({ provenance: [] });

    // Act
    render(<CourseReader course={course} />);

    // Assert
    expect(screen.getByText(/no source on record/i)).toBeInTheDocument();
  });

  it("surfaces a cut claim's status independent of its citation", () => {
    // Arrange — a cut claim that still resolves a citation, isolating the status from the source path.
    const course = courseWithDemonstrateClaim({
      text: "An unsupported assertion.",
      supportedBy: "src-1",
      verifierStatus: "cut",
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert
    expect(screen.getByText("An unsupported assertion.")).toBeInTheDocument();
    expect(screen.getByText("CUT")).toBeInTheDocument();
  });
});

describe("CourseReader — lesson body", () => {
  it("renders the four teaching phases, relabelled to the lesson arc (P7.3)", () => {
    // Arrange / Act
    render(<CourseReader course={moduleWithObjectivesAndAssessment()} />);

    // Assert — the Merrill phases now read as the arc's teaching rhythm.
    expect(screen.getByRole("heading", { name: "Warm-up" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Strategies & worked example" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Practice" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Make it your own" })).toBeInTheDocument();
  });

  it("shows the module's Bloom-tagged objectives on its first lesson only", () => {
    // Arrange / Act — the first lesson is focused by default.
    render(<CourseReader course={moduleWithObjectivesAndAssessment()} />);

    // Assert — objectives + Bloom level are present on the module's opening lesson.
    expect(screen.getByText(/learning objectives/i)).toBeInTheDocument();
    expect(
      screen.getByText("Locate a target in a sorted array with binary search."),
    ).toBeInTheDocument();
    expect(screen.getByText("apply")).toBeInTheDocument();

    // Act — move off the first lesson; objectives no longer show.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));
    expect(screen.queryByText(/learning objectives/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText("Locate a target in a sorted array with binary search."),
    ).not.toBeInTheDocument();
  });

  it("renders the lesson arc: what it expects, the module competency, and a self-check (P7.3)", () => {
    // Arrange / Act — the default course carries the arc compartments + module competency.
    render(<CourseReader course={makeCourse()} />);

    // Assert — the arc opens with entry expectations and closes with a self-check, and the lesson
    // shows the competency its module builds toward.
    expect(screen.getByRole("heading", { name: "What this lesson expects" })).toBeInTheDocument();
    expect(
      screen.getByText("You can compare two numbers and recognise a sorted list."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Self-check" })).toBeInTheDocument();
    expect(
      screen.getByText("Can you locate 7 in a 9-element sorted array in at most 4 comparisons?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Locate an element in a sorted collection efficiently\./),
    ).toBeInTheDocument();
  });

  it("omits the arc compartments for a course built before P7.3 (no expects / self-check)", () => {
    // Arrange — a pre-P7.3 lesson with empty arc fields and a module with no competency.
    const bare = makeCourse({
      modules: [
        makeModule({ lessons: [makeLesson({ expects: [], selfCheck: [] })], competency: null }),
      ],
    });

    // Act
    render(<CourseReader course={bare} />);

    // Assert — the arc sections simply do not render (no empty headings), and no competency line.
    expect(
      screen.queryByRole("heading", { name: "What this lesson expects" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Self-check" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Builds toward/)).not.toBeInTheDocument();
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
