import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LessonScaffold } from "./LessonScaffold";

describe("LessonScaffold", () => {
  it("renders the title, cue, and each item as a labelled region", () => {
    // Arrange / Act
    render(
      <LessonScaffold
        title="What this lesson expects"
        cue="What to be comfortable with before you start"
        items={["You can form complex sentences.", "You know the past perfect tense."]}
      />,
    );

    // Assert — the panel is a region named by its title (screen-reader navigable), with the cue and
    // every item rendered.
    const region = screen.getByRole("region", { name: "What this lesson expects" });
    expect(region).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What this lesson expects" })).toBeInTheDocument();
    expect(screen.getByText("What to be comfortable with before you start")).toBeInTheDocument();
    expect(screen.getByText("You can form complex sentences.")).toBeInTheDocument();
    expect(screen.getByText("You know the past perfect tense.")).toBeInTheDocument();
  });

  it("renders no list items when given an empty list (must not assume the caller's guard)", () => {
    // Arrange / Act — the caller guards on items.length, but the component must not crash on [].
    render(<LessonScaffold title="Self-check" cue="Confirm you've got it" items={[]} />);

    // Assert — the panel still renders its title, but there are no item rows.
    expect(screen.getByRole("region", { name: "Self-check" })).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
