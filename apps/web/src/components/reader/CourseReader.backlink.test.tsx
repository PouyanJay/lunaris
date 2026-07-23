import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCourse } from "../../test/fixtures";
import { CourseReader } from "./CourseReader";

/** Claim → lesson backlink (claim-lesson-backlink): clicking a claim in the Sources & checks rail
 *  jumps the Learn Focus-Flow to where that claim lives in the lesson. The rail is a static column,
 *  so the claim button is reachable without opening a drawer. */
describe("CourseReader — claim → lesson backlink", () => {
  it("jumps the Focus Flow to the claim's phase when its rail entry is clicked", () => {
    // Arrange — Learn mode opens on step 1 (the intro/expects bookend). The fixture's only claim
    // lives in the demonstrate phase ("Strategies & worked example").
    render(<CourseReader course={makeCourse()} />);
    expect(screen.getByText(/you can compare two numbers/i)).toBeInTheDocument(); // intro step

    // Act — click the claim in the rail (its button is labelled "Locate in the lesson: <claim>").
    fireEvent.click(
      screen.getByRole("button", {
        name: "Locate in the lesson: Comparison reduces the problem size each step.",
      }),
    );

    // Assert — the flow moved to the demonstrate content step (the step card's eyebrow names its
    // section), and we've left the intro. The rail entry is now the active/pressed one.
    const card = screen.getByRole("group", { name: "Step content" });
    expect(within(card).getByText(/Strategies & worked example/)).toBeInTheDocument();
    expect(screen.queryByText(/you can compare two numbers/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Locate in the lesson: Comparison reduces the problem size each step.",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("jumps to the exact chunk that holds the claim's sentence, not just the phase", () => {
    // Arrange — a lesson whose demonstrate phase spans TWO content chunks: a ~130-word filler
    // (chunk 1) then a short paragraph carrying the claim's sentence (chunk 2). Every other section
    // is emptied so the flow is exactly [chunk1, chunk2] — step 1 and step 2.
    const filler = `${Array.from({ length: 130 }, (_, i) => `w${i}`).join(" ")}.`;
    const course = makeCourse();
    const lesson = course.modules[0]!.lessons[0]!;
    lesson.segments.activate.prose = "";
    lesson.segments.apply.prose = "";
    lesson.segments.integrate.prose = "";
    lesson.segments.demonstrate.prose = `${filler}\n\nThe zephyr protocol encrypts the quokka channel.`;
    lesson.segments.demonstrate.resources = [];
    lesson.segments.demonstrate.claims = [
      { text: "Zephyr protocol encrypts the quokka channel", supportedBy: null, verifierStatus: "cut" },
    ];
    lesson.expects = [];
    lesson.selfCheck = [];
    course.modules[0]!.assessment.items = [];

    render(<CourseReader course={course} />);
    // The flow opens on chunk 1 (the filler).
    expect(screen.getByText(/step 1 of 2/i)).toBeInTheDocument();

    // Act — locate the claim whose sentence lives in chunk 2.
    fireEvent.click(
      screen.getByRole("button", {
        name: "Locate in the lesson: Zephyr protocol encrypts the quokka channel",
      }),
    );

    // Assert — it jumped past the phase's first step to chunk 2 (sentence precision, not the
    // phase-first fallback, which would have stayed on step 1).
    expect(screen.getByText(/step 2 of 2/i)).toBeInTheDocument();
  });
});
