import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkedExample } from "./WorkedExample";

describe("WorkedExample", () => {
  it("renders both labelled sides and the why note", () => {
    // Arrange / Act
    render(
      <WorkedExample
        literal={{ label: "Literal", text: "We will work very hard." }}
        improved={{ label: "With collocation", text: "We will do the heavy lifting." }}
        note="'do the heavy lifting' suits a professional tone."
      />,
    );

    // Assert — both sides, their labels, and the note (with its "Why" marker) are present.
    expect(screen.getByText("Literal")).toBeInTheDocument();
    expect(screen.getByText("We will work very hard.")).toBeInTheDocument();
    expect(screen.getByText("With collocation")).toBeInTheDocument();
    expect(screen.getByText("We will do the heavy lifting.")).toBeInTheDocument();
    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(screen.getByText(/suits a professional tone/)).toBeInTheDocument();
  });

  it("omits the note row when there is no note", () => {
    // Arrange / Act
    render(
      <WorkedExample
        literal={{ label: "Before", text: "a" }}
        improved={{ label: "After", text: "b" }}
        note={null}
      />,
    );

    // Assert — no "Why" marker when the note is absent (nothing to explain).
    expect(screen.queryByText("Why")).not.toBeInTheDocument();
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
  });
});
