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
});
