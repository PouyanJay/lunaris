import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Claim, Lesson, Visual } from "../../types/course";
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH } from "../../hooks/useRailLayout";
import { makeCitation, makeCourse, makeLesson, makeModule } from "../../test/fixtures";
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
    segments: {
      ...base.segments,
      activate: { prose: activateProse, visuals: [], claims: [], resources: [] },
    },
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
      resources: [],
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

  it("shows an honest scope caveat when the course could not be grounded (CQ Phase 1.6)", () => {
    // Arrange — a course carrying a scope note (a research-needing goal that wasn't grounded).
    const note = "This course could not be grounded in CLB 10's real requirements.";
    const course = makeCourse({ scopeNote: note });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the caveat is shown as a labeled warning the learner can't miss.
    const caveat = screen.getByRole("complementary", { name: /warning/i });
    expect(caveat).toHaveTextContent(note);
  });

  it("shows no scope caveat when the course is grounded (empty scope note)", () => {
    // Arrange / Act — the default fixture has an empty scopeNote.
    render(<CourseReader course={makeCourse()} />);

    // Assert
    expect(screen.queryByRole("complementary", { name: /warning/i })).not.toBeInTheDocument();
  });

  it("shows the scope-realism band at the course entry (CQ Phase 3.1)", () => {
    // Arrange — a course carrying a computed scope band.
    const course = makeCourse({
      scope: {
        effort: "About 4-9 weeks of self-paced study (~20-35 hours).",
        delivers: ["A structured understanding of binary search."],
        excludes: ["It will not certify you."],
      },
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the band mounts and its data flows through (per-item rendering is covered in
    // ScopeBand.test.tsx; here we prove the integration).
    const band = screen.getByRole("region", { name: /course scope/i });
    expect(within(band).getByText(/4-9 weeks/)).toBeInTheDocument();
    expect(
      within(band).getByText("A structured understanding of binary search."),
    ).toBeInTheDocument();
  });

  it("shows no scope band when the course has none (pre-Phase-3 course)", () => {
    // Arrange / Act — the default fixture omits `scope`.
    render(<CourseReader course={makeCourse()} />);

    // Assert
    expect(screen.queryByRole("region", { name: /course scope/i })).not.toBeInTheDocument();
  });

  it("shows the scope band only at the entry, not on a later lesson", () => {
    // Arrange — a multi-lesson course with a scope band.
    const course = multiLessonCourse();
    course.scope = {
      effort: "About 3-6 weeks of self-paced study (~12-20 hours).",
      delivers: ["A working grasp of the foundations."],
      excludes: ["It will not certify you."],
    };
    render(<CourseReader course={course} />);

    // Assert (precondition) — the band is visible on the entry lesson.
    expect(screen.getByRole("region", { name: /course scope/i })).toBeInTheDocument();

    // Act — advance to the next lesson.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));

    // Assert — the orientation band is an entry header, not repeated on every lesson.
    expect(screen.queryByRole("region", { name: /course scope/i })).not.toBeInTheDocument();
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
                demonstrate: { prose: "Demo.", visuals: [visual], claims: [], resources: [] },
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
              // Required by the type; its rendering is asserted in T5 (LessonAssessment).
              passCriterion: "States O(log n).",
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
              demonstrate: { prose: "Demonstration.", visuals: [], claims: [claim], resources: [] },
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

  it("renders a phase's curated resources as out-bound links with source + trust (P7.4)", () => {
    // Arrange / Act — the default lesson carries a video resource on its demonstrate phase.
    render(<CourseReader course={makeCourse()} />);

    // Assert — the resource shows as a new-tab link, with its source domain and trust tier.
    const link = screen.getByRole("link", { name: "Binary search visualised" });
    expect(link).toHaveAttribute("href", "https://www.youtube.com/watch?v=demo");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("youtube.com")).toBeInTheDocument();
    // Trust tier shows in the word, not colour alone (WCAG: never colour as the sole signal).
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByText("A 6-min animation of halving the search range.")).toBeInTheDocument();
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

/** A single-lesson course whose demonstrate prose contains a sentence the claim text overlaps, so
 *  the best-effort matcher links the claim to that exact sentence (the precise-highlight path). */
function courseWithMatchingSentence() {
  const base = makeLesson();
  return makeCourse({
    modules: [
      makeModule({
        lessons: [
          {
            ...base,
            segments: {
              ...base.segments,
              demonstrate: {
                prose:
                  "Subordinate clauses name the logical relationship between ideas. " +
                  "Then you revise your own paragraph carefully.",
                visuals: [],
                claims: [
                  {
                    text: "Subordinate clauses name the logical relationship clearly.",
                    supportedBy: "src-1",
                    verifierStatus: "supported",
                  },
                ],
                resources: [],
              },
            },
          },
        ],
      }),
    ],
  });
}

describe("CourseReader — annotation rail & cross-highlight", () => {
  it("lifts claims into the Sources & checks rail, out of the reading column", () => {
    // Arrange / Act — the default course has a demonstrate claim.
    render(<CourseReader course={makeCourse()} />);

    // Assert — the claim lives in the complementary rail region…
    const rail = screen.getByRole("complementary", { name: /sources and checks/i });
    expect(
      within(rail).getByText("Comparison reduces the problem size each step."),
    ).toBeInTheDocument();
    expect(within(rail).getByText("SUPPORTED")).toBeInTheDocument();

    // …and NOT inline in the reading column (the contract is "moved out of the prose").
    const column = screen.getByRole("region", { name: /lesson reader/i });
    expect(
      within(column).queryByText("Comparison reduces the problem size each step."),
    ).not.toBeInTheDocument();
    expect(within(column).queryByText("SUPPORTED")).not.toBeInTheDocument();
  });

  it("shows the source's trust tier in the rail for a classified citation", () => {
    // Arrange — a course whose provenance carries a classified (trust-scored) citation.
    const course = makeCourse({
      provenance: [makeCitation({ id: "src-1", trustTier: "reputable", credibility: 0.91 })],
    });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the tier reaches the rail through the real annotation chain (never colour alone).
    const rail = screen.getByRole("complementary", { name: /sources and checks/i });
    expect(within(rail).getByText("reputable")).toBeInTheDocument();
    expect(within(rail).getByText("91%")).toBeInTheDocument();
  });

  it("clears the active cross-highlight when navigating to another lesson", () => {
    // Arrange — lesson 1 has a matchable claim; lesson 2 has none.
    const matching = courseWithMatchingSentence();
    const course = makeCourse({
      modules: [
        { ...matching.modules[0]!, id: "m1", title: "One" },
        makeModule({ id: "m2", title: "Two", lessons: [lessonWith("l2", "Second lesson prose.")] }),
      ],
    });
    render(<CourseReader course={course} />);
    fireEvent.click(screen.getByRole("button", { name: /locate in the lesson/i }));
    expect(screen.getByRole("button", { name: /show the source note for/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Act — advance to the next lesson.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));

    // Assert — the stale highlight is cleared (no marked sentence remains pressed).
    expect(
      screen.queryByRole("button", { name: /show the source note for/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Second lesson prose.")).toBeInTheDocument();
  });

  it("cross-highlights between a matched prose sentence and its rail entry (both directions)", () => {
    // Arrange — a course where the claim matches a demonstrate sentence.
    render(<CourseReader course={courseWithMatchingSentence()} />);
    const railEntry = screen.getByRole("button", { name: /locate in the lesson/i });
    const proseMark = screen.getByRole("button", { name: /show the source note for/i });
    expect(railEntry).toHaveAttribute("aria-pressed", "false");
    expect(proseMark).toHaveAttribute("aria-pressed", "false");

    // Act / Assert — selecting the rail entry highlights the matched sentence.
    fireEvent.click(railEntry);
    expect(proseMark).toHaveAttribute("aria-pressed", "true");

    // Act / Assert — selecting the prose sentence highlights the rail entry.
    fireEvent.click(proseMark);
    expect(railEntry).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to highlighting the whole phase when a claim has no sentence match", () => {
    // Arrange — the default claim does not overlap its prose, so it links to the phase.
    render(<CourseReader course={makeCourse()} />);

    // Act — select the (fallback) rail entry.
    fireEvent.click(screen.getByRole("button", { name: /locate in the lesson/i }));

    // Assert — the demonstrate phase is marked active for the highlight.
    expect(document.querySelector('[data-phase="demonstrate"]')).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("toggles the annotation drawer and closes it on Escape", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const toggle = screen.getByRole("button", { name: /sources & checks/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    // Act / Assert — the toggle opens the drawer…
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    // …and Escape closes it and returns focus to the toggle (keyboard orientation).
    fireEvent.keyDown(window, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.activeElement).toBe(toggle);
  });

  it("collapses the rail on wide screens and offers a reveal control", () => {
    // Arrange — the default course has rail annotations, so the wide-screen controls render.
    const { container } = render(<CourseReader course={makeCourse()} />);
    expect(container.querySelector('[data-rail-collapsed="true"]')).toBeNull();

    // Act — collapse the rail.
    fireEvent.click(screen.getByRole("button", { name: /collapse sources and checks/i }));

    // Assert — the reader marks the rail collapsed and surfaces a reveal tab.
    expect(container.querySelector('[data-rail-collapsed="true"]')).not.toBeNull();
    const reveal = screen.getByRole("button", { name: /show sources and checks/i });

    // Act / Assert — revealing restores the expanded layout.
    fireEvent.click(reveal);
    expect(container.querySelector('[data-rail-collapsed="true"]')).toBeNull();
  });

  it("exposes a keyboard-resizable rail splitter advertising its width bounds", () => {
    // Arrange
    render(<CourseReader course={makeCourse()} />);
    const splitter = screen.getByRole("separator", { name: /resize sources and checks/i });
    expect(splitter).toHaveAttribute("aria-valuemin", String(RAIL_MIN_WIDTH));
    expect(splitter).toHaveAttribute("aria-valuemax", String(RAIL_MAX_WIDTH));
    const start = Number(splitter.getAttribute("aria-valuenow"));

    // Act — ArrowLeft widens the rail (it sits on the right edge).
    fireEvent.keyDown(splitter, { key: "ArrowLeft" });

    // Assert — the advertised width grows.
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBeGreaterThan(start);
  });
});

describe("CourseReader — outline drawer (mobile)", () => {
  const lessonsToggle = () => screen.getByRole("button", { name: /^lessons$/i });

  it("opens the lesson outline from the reader-bar toggle", () => {
    // Arrange
    render(<CourseReader course={multiLessonCourse()} />);
    expect(lessonsToggle()).toHaveAttribute("aria-expanded", "false");

    // Act
    fireEvent.click(lessonsToggle());

    // Assert — the toggle advertises the open drawer.
    expect(lessonsToggle()).toHaveAttribute("aria-expanded", "true");
  });

  it("navigates and closes the drawer when a lesson is picked from it", () => {
    // Arrange — open the outline.
    render(<CourseReader course={multiLessonCourse()} />);
    fireEvent.click(lessonsToggle());

    // Act — pick a lesson from the open outline.
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 3/i }));

    // Assert — the chosen lesson shows and the drawer has closed behind it.
    expect(screen.getByText("Prose for lesson three.")).toBeInTheDocument();
    expect(lessonsToggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the outline drawer on Escape and returns focus to the toggle", () => {
    // Arrange
    render(<CourseReader course={multiLessonCourse()} />);
    fireEvent.click(lessonsToggle());

    // Act
    fireEvent.keyDown(window, { key: "Escape" });

    // Assert
    expect(lessonsToggle()).toHaveAttribute("aria-expanded", "false");
    expect(lessonsToggle()).toHaveFocus();
  });
});
