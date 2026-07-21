import { StrictMode } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Claim } from "../../types/course";
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH } from "../../hooks/useRailLayout";
import { makeCitation, makeCourse, makeLesson, makeModule, routedFetch } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

const API = "http://api.test";

/** routedFetch with a settled (empty) progress snapshot — enough for the online Watch-mode tests
 *  (which need a reachable video service for Watch to be offered). No lesson ships a video, so the
 *  video hook stays idle and never fetches; the footer's lesson paging is what we exercise. */
function readerFetch() {
  return routedFetch({ progress: { courseId: "course-test", objectives: [], lessons: [] } });
}

/** A distinctly-id'd lesson. Lessons no longer identify by their prose (Learn steps through it and
 *  Watch plays the video), so the reader's tests key off position ("Lesson N of M") and the outline
 *  instead — this keeps the ids/module grouping the navigation tests rely on. */
function lessonWith(id: string): ReturnType<typeof makeLesson> {
  return makeLesson({ id });
}

/** Two modules, three lessons total — enough to exercise outline grouping and Prev/Next bounds. */
function multiLessonCourse() {
  return makeCourse({
    modules: [
      makeModule({
        id: "m1",
        title: "Foundations",
        lessons: [lessonWith("l1"), lessonWith("l2")],
      }),
      makeModule({
        id: "m2",
        title: "Search",
        lessons: [lessonWith("l3")],
      }),
    ],
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// Offline reader (no apiBaseUrl) → Learn is the only mode; these cover the mode-independent shell:
// the outline, scope furniture, the empty state, and outline-driven lesson navigation.
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
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /lesson 3/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
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

    // Act — advance to a later lesson (via the outline — the mode-independent navigation door).
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 2/i }));

    // Assert — the orientation band is an entry header, not repeated on every lesson.
    expect(screen.queryByRole("region", { name: /course scope/i })).not.toBeInTheDocument();
  });

  it("renders an empty state when no lessons are authored", () => {
    // Arrange / Act
    render(<CourseReader course={makeCourse({ modules: [] })} />);

    // Assert
    expect(screen.getByRole("status")).toHaveTextContent(/no lessons/i);
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
          lessons: [lessonWith("l1"), lessonWith("l2")],
        }),
        makeModule({
          id: "m2",
          title: "Search",
          kcs: ["binary_search"],
          lessons: [lessonWith("l3")],
        }),
      ],
    });
    const { rerender } = render(<CourseReader course={course} />);
    expect(screen.getByText(/lesson 1 of 3/i)).toBeInTheDocument();

    // Act — a drill-in request targeting binary_search.
    rerender(<CourseReader course={course} focusRequest={{ kc: "binary_search", seq: 1 }} />);

    // Assert — the reader jumps to that module's lesson.
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
  });

  it("honours a mount-time focus request under StrictMode's effect replay", () => {
    // Regression guard for a bug live verification caught: StrictMode remounts replay effects,
    // and an unguarded course-reset effect zeroed the index AFTER the (once-consumed) focus
    // request had been applied — dev landed on lesson 1 while non-StrictMode tests passed.
    const course = makeCourse({
      modules: [
        makeModule({
          id: "m1",
          title: "Foundations",
          lessons: [lessonWith("l1")],
        }),
        makeModule({
          id: "m2",
          title: "Search",
          kcs: ["binary_search"],
          lessons: [lessonWith("l2")],
        }),
      ],
    });

    render(
      <StrictMode>
        <CourseReader course={course} focusRequest={{ kc: "binary_search", seq: 1 }} />
      </StrictMode>,
    );

    expect(screen.getByText(/lesson 2 of 2/i)).toBeInTheDocument();
  });
});

describe("CourseReader — regenerate", () => {
  it("regenerates the focused lesson and swaps in the returned course", async () => {
    // Arrange — a handler returning a course whose module competency changed (a signal visible in
    // the lesson header regardless of mode).
    const updated = makeCourse();
    updated.modules[0]!.competency = "Reason about logarithmic search precisely.";
    const onRegenerate = vi.fn().mockResolvedValue(updated);
    const course = makeCourse();
    const originalCompetency = course.modules[0]!.competency!;
    render(<CourseReader course={course} onRegenerate={onRegenerate} />);
    expect(screen.getByText(new RegExp(originalCompetency))).toBeInTheDocument();

    // Act
    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));

    // Assert — the handler gets the focused lesson id, and the updated course replaces the old.
    expect(onRegenerate).toHaveBeenCalledWith(course.modules[0]!.lessons[0]!.id);
    expect(
      await screen.findByText(/Reason about logarithmic search precisely\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(originalCompetency))).not.toBeInTheDocument();
  });
});

// Watch is where the lesson video lives — and, with Read retired, where per-lesson footer paging and
// the Overview exit now live. These need an online reader (apiBaseUrl) so Watch is offered.
describe("CourseReader — Watch-mode footer navigation", () => {
  function renderWatch(course = multiLessonCourse(), props = {}) {
    localStorage.setItem(READER_MODE_KEY, "watch");
    vi.stubGlobal("fetch", readerFetch());
    return render(<CourseReader course={course} apiBaseUrl={API} {...props} />);
  }

  it("renders the footer: worded labels with the advance as the accent CTA", async () => {
    // The advancing action is the reader's one amber CTA (P6); Previous stays neutral.
    renderWatch();
    await screen.findByRole("radio", { name: /watch/i });

    const next = screen.getByRole("button", { name: /next lesson/i });
    expect(next).toHaveTextContent("Next lesson");
    expect(next.className).toMatch(/accent/);
    expect(screen.getByRole("button", { name: /previous lesson/i })).toHaveTextContent("Previous");

    // On the last lesson the advance becomes Finish course — still the accent CTA.
    fireEvent.click(next);
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));
    const finish = screen.getByRole("button", { name: /finish course/i });
    expect(finish.className).toMatch(/accent/);
  });

  it("steps forward with Next and swaps in Finish on the last lesson", async () => {
    // Arrange
    renderWatch();
    await screen.findByRole("radio", { name: /watch/i });

    // Act — advance through every lesson.
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));
    expect(screen.getByText(/lesson 2 of 3/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));

    // Assert — the last lesson is focused; Next has given way to Finish course.
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next lesson/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /finish course/i })).toBeInTheDocument();
  });

  it("steps back with Previous and disables it on the first lesson", async () => {
    // Arrange — start on the last lesson.
    renderWatch();
    await screen.findByRole("radio", { name: /watch/i });
    const outline = screen.getByRole("navigation", { name: /course outline/i });
    fireEvent.click(within(outline).getByRole("button", { name: /lesson 3/i }));
    const prev = screen.getByRole("button", { name: /previous lesson/i });

    // Act — step back one lesson.
    fireEvent.click(prev);
    expect(screen.getByText(/lesson 2 of 3/i)).toBeInTheDocument();

    // Act / Assert — stepping back to the first lesson disables Previous.
    fireEvent.click(prev);
    expect(screen.getByText(/lesson 1 of 3/i)).toBeInTheDocument();
    expect(prev).toBeDisabled();
  });

  it("offers an Overview exit instead of a dead Prev on the first lesson", async () => {
    // Arrange
    const onExitToOverview = vi.fn();
    renderWatch(multiLessonCourse(), { onExitToOverview });
    await screen.findByRole("radio", { name: /watch/i });

    // Act — on lesson 1 the back affordance leads out to the Overview (the design's prev-label
    // rule) rather than sitting disabled.
    fireEvent.click(screen.getByRole("button", { name: /back to overview/i }));

    // Assert
    expect(onExitToOverview).toHaveBeenCalledTimes(1);
  });

  it("keeps Prev as lesson navigation past the first lesson", async () => {
    // Arrange
    const onExitToOverview = vi.fn();
    renderWatch(multiLessonCourse(), { onExitToOverview });
    await screen.findByRole("radio", { name: /watch/i });
    fireEvent.click(screen.getByRole("button", { name: /next lesson/i }));

    // Act
    fireEvent.click(screen.getByRole("button", { name: /previous lesson/i }));

    // Assert — back on lesson 1 without leaving the reader.
    expect(onExitToOverview).not.toHaveBeenCalled();
    expect(screen.getByText(/lesson 1 of/i)).toBeInTheDocument();
  });
});

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

    // Assert — the claim, its status, and the resolved citation (a real outbound link) all show in
    // the Sources & checks rail.
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

describe("CourseReader — annotation rail", () => {
  it("lifts claims into the Sources & checks rail, out of the reading column", () => {
    // Arrange / Act — the default course has a demonstrate claim.
    render(<CourseReader course={makeCourse()} />);

    // Assert — the claim lives in the complementary rail region…
    const rail = screen.getByRole("complementary", { name: /sources and checks/i });
    expect(
      within(rail).getByText("Comparison reduces the problem size each step."),
    ).toBeInTheDocument();
    expect(within(rail).getByText("SUPPORTED")).toBeInTheDocument();

    // …and NOT inline in the reading column (the contract is "moved out of the lesson body").
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

  it("the header Sources toggle collapses and restores the rail on wide screens", () => {
    // Arrange — jsdom's matchMedia reports wide, where the rail is a visible column.
    const { container } = render(<CourseReader course={makeCourse()} />);
    const toggle = screen.getByRole("button", { name: /sources & checks/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("data-open", "true");

    // Act / Assert — one labelled control drives the rail everywhere (P6): here it collapses…
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelector('[data-rail-collapsed="true"]')).not.toBeNull();

    // …and restores.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector('[data-rail-collapsed="true"]')).toBeNull();
  });

  it("toggles the annotation drawer and closes it on Escape below the rail breakpoint", () => {
    // Arrange — simulate the narrow layout, where the rail is an off-canvas drawer.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("1100px"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
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
    expect(screen.getByText(/lesson 3 of 3/i)).toBeInTheDocument();
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
