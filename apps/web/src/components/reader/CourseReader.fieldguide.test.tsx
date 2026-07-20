import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Segment } from "../../types/course";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

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
