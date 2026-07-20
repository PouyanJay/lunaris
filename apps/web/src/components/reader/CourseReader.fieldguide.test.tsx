import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Segment } from "../../types/course";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

function proseSegment(prose: string): Segment {
  return { prose, visuals: [], claims: [], resources: [] };
}

/** A lesson whose four phases total ~660 words — a 3-minute read at 220 wpm. */
function longLesson() {
  const words = (count: number, prefix: string) =>
    Array.from({ length: count }, (_, i) => `${prefix}${i}`).join(" ");
  return makeLesson({
    segments: {
      activate: proseSegment(words(200, "a")),
      demonstrate: proseSegment(words(200, "d")),
      apply: proseSegment(words(130, "p")),
      integrate: proseSegment(words(130, "i")),
    },
    expects: [],
    selfCheck: [],
  });
}

/** Field Guide (lesson-experience redesign phase 1): the reading-meta band. */
// These suites exercise the long-form Read mode (Focus Flow's Learn mode is the default) —
// pin the persisted preference before each render.
beforeEach(() => {
  localStorage.setItem(READER_MODE_KEY, "read");
});

describe("CourseReader — reading meta band", () => {
  it("shows the focused lesson's estimated reading time derived from its prose", () => {
    // Arrange
    const course = makeCourse({ modules: [makeModule({ lessons: [longLesson()] })] });

    // Act
    render(<CourseReader course={course} />);

    // Assert — the band is a labelled group carrying the mono reading-time metric.
    const band = screen.getByRole("group", { name: /reading progress/i });
    expect(band).toHaveTextContent(/3 min read/i);
  });

  it("advances the percent read as the reading pane scrolls", async () => {
    // Arrange — jsdom has no layout, so give the pane a scrollable geometry by hand.
    render(<CourseReader course={makeCourse()} />);
    const pane = screen.getByRole("region", { name: "Lesson reader" });
    Object.defineProperty(pane, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(pane, "clientHeight", { configurable: true, value: 1000 });
    Object.defineProperty(pane, "scrollTop", { configurable: true, value: 500, writable: true });

    // Act — half-way through the scrollable range.
    fireEvent.scroll(pane);

    // Assert
    await waitFor(() => {
      expect(screen.getByRole("group", { name: /reading progress/i })).toHaveTextContent(
        /50% read/i,
      );
    });
  });

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

  it("scrolls the pane to a section chosen from the outline", () => {
    // Arrange — jsdom has no scrollIntoView; install one on the Practice section to observe.
    render(<CourseReader course={makeCourse()} />);
    const target = document.querySelector('[data-section="apply"]') as HTMLElement;
    const scrolled = vi.fn();
    target.scrollIntoView = scrolled;
    const outline = screen.getByRole("navigation", { name: "Course outline" });

    // Act
    fireEvent.click(within(outline).getByRole("button", { name: /practice/i }));

    // Assert
    expect(scrolled).toHaveBeenCalled();
  });

  it("marks scrolled-past sections done and the section in view current", async () => {
    // Arrange — hand the pane and sections a real geometry (jsdom lays out nothing).
    render(<CourseReader course={makeCourse()} />);
    const pane = screen.getByRole("region", { name: "Lesson reader" });
    const rect = (top: number, bottom: number) =>
      ({ top, bottom, height: bottom - top }) as DOMRect;
    pane.getBoundingClientRect = () => rect(0, 800);
    const geometry: Record<string, DOMRect> = {
      expects: rect(-900, -700),
      activate: rect(-700, -100),
      demonstrate: rect(-100, 600),
      apply: rect(600, 1200),
      integrate: rect(1200, 1500),
      selfCheck: rect(1500, 1700),
      assessment: rect(1700, 1900),
    };
    for (const [id, sectionRect] of Object.entries(geometry)) {
      const el = document.querySelector(`[data-section="${id}"]`) as HTMLElement;
      el.getBoundingClientRect = () => sectionRect;
    }

    // Act
    fireEvent.scroll(pane);

    // Assert — Warm-up is fully above the pane (done); the worked example is in view (current).
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    await waitFor(() => {
      expect(within(outline).getByRole("button", { name: /warm-up/i })).toHaveAttribute(
        "data-state",
        "done",
      );
      expect(within(outline).getByRole("button", { name: /worked example/i })).toHaveAttribute(
        "aria-current",
        "location",
      );
      expect(within(outline).getByRole("button", { name: /practice/i })).toHaveAttribute(
        "data-state",
        "upcoming",
      );
    });
  });

  it("summarises later module lessons with the 30-second TL;DR, not the first", () => {
    // Arrange — two lessons in the one module. The first lesson carries the full objectives
    // panel, so it must NOT also show the TL;DR; the second gets the module-wide summary.
    const course = makeCourse();
    course.modules[0]!.lessons = [makeLesson(), makeLesson({ id: "m-binary_search-l1" })];
    render(<CourseReader course={course} />);
    expect(screen.queryByText("This lesson in 30 seconds")).not.toBeInTheDocument();

    // Act — open the module's SECOND lesson.
    fireEvent.click(screen.getByRole("button", { name: "Next lesson" }));

    // Assert — the summary panel is present with the de-scaffolded objective.
    expect(screen.getByText("This lesson in 30 seconds")).toBeInTheDocument();
    expect(screen.getByText("Locate a target with binary search.")).toBeInTheDocument();
  });

  it("hides the TL;DR when the module has no objectives", () => {
    // Arrange — makeModule defaults to zero objectives.
    const course = makeCourse({ modules: [makeModule()] });

    // Act
    render(<CourseReader course={course} />);

    // Assert
    expect(screen.queryByText("This lesson in 30 seconds")).not.toBeInTheDocument();
  });

  it("marks a knowledge component's name in prose with its graph definition", async () => {
    // Arrange — the fixture's demonstrate prose opens "Binary search halves…" and the graph
    // defines the Binary Search KC. No :term directive is authored anywhere.
    render(<CourseReader course={makeCourse()} />);

    // Act — focus the auto-marked term.
    const term = screen.getByRole("button", { name: "Binary search" });
    fireEvent.focus(term);

    // Assert — the KC's own definition surfaces as the tooltip.
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Halving a sorted range each step.",
    );
  });

  it("renders a bare-arc lesson with only the four phase sections", () => {
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

    // Assert — the section level holds exactly the phases; no bookend entries, no TL;DR, and
    // the reader still shows the meta band.
    const outline = screen.getByRole("navigation", { name: "Course outline" });
    expect(within(outline).getByRole("button", { name: /warm-up/i })).toBeInTheDocument();
    expect(within(outline).queryByRole("button", { name: /self-check/i })).not.toBeInTheDocument();
    expect(
      within(outline).queryByRole("button", { name: /check your understanding/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /reading progress/i })).toBeInTheDocument();
  });

  it("survives a course whose graph defines no glossary terms", () => {
    // Arrange — empty graph: no definitions to propagate.
    const course = makeCourse();
    course.graph.nodes = [];

    // Act / Assert — prose renders untouched, nothing crashes.
    render(<CourseReader course={course} />);
    expect(screen.getByText(/binary search halves the candidate range/i)).toBeInTheDocument();
  });

  it("caps the read percent at 100 and drops the time-left metric at the end", async () => {
    // Arrange — scrolled past the end (momentum overshoot).
    render(<CourseReader course={makeCourse()} />);
    const pane = screen.getByRole("region", { name: "Lesson reader" });
    Object.defineProperty(pane, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(pane, "clientHeight", { configurable: true, value: 1000 });
    Object.defineProperty(pane, "scrollTop", { configurable: true, value: 1200, writable: true });

    // Act
    fireEvent.scroll(pane);

    // Assert
    await waitFor(() => {
      const band = screen.getByRole("group", { name: /reading progress/i });
      expect(band).toHaveTextContent(/100% read/i);
      expect(band).not.toHaveTextContent(/min left/i);
    });
  });

  it("shows the remaining reading time once underway", async () => {
    // Arrange — a 3-minute lesson, half read → 2 minutes left (ceiling).
    const course = makeCourse({ modules: [makeModule({ lessons: [longLesson()] })] });
    render(<CourseReader course={course} />);
    const pane = screen.getByRole("region", { name: "Lesson reader" });
    Object.defineProperty(pane, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(pane, "clientHeight", { configurable: true, value: 1000 });
    Object.defineProperty(pane, "scrollTop", { configurable: true, value: 500, writable: true });

    // Act
    fireEvent.scroll(pane);

    // Assert
    await waitFor(() => {
      expect(screen.getByRole("group", { name: /reading progress/i })).toHaveTextContent(
        /2 min left/i,
      );
    });
  });
});
