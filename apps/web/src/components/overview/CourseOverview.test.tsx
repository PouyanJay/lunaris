import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CourseOverview } from "./CourseOverview";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";

describe("CourseOverview", () => {
  it("counts the course's lessons and concepts", () => {
    // Arrange — two modules (1 + 2 lessons) over the fixture's three-concept graph.
    const course = makeCourse({
      modules: [
        makeModule({ id: "m-1", lessons: [makeLesson({ id: "m-1-l0" })] }),
        makeModule({
          id: "m-2",
          lessons: [makeLesson({ id: "m-2-l0" }), makeLesson({ id: "m-2-l1" })],
        }),
      ],
    });

    // Act
    render(<CourseOverview course={course} onContinue={vi.fn()} onViewMap={vi.fn()} />);

    // Assert
    expect(screen.getByText("3 lessons · 3 concepts")).toBeInTheDocument();
  });

  it("uses singular forms for a one-lesson, one-concept course", () => {
    // Arrange
    const course = makeCourse({
      modules: [makeModule({ lessons: [makeLesson()] })],
      graph: {
        nodes: [
          {
            id: "kc",
            label: "KC",
            definition: "",
            difficulty: 0.5,
            bloomCeiling: "understand",
            sources: [],
          },
        ],
        edges: [],
        frontier: [],
        isAcyclic: true,
        topoOrder: ["kc"],
      },
    });

    // Act
    render(<CourseOverview course={course} onContinue={vi.fn()} onViewMap={vi.fn()} />);

    // Assert
    expect(screen.getByText("1 lesson · 1 concept")).toBeInTheDocument();
  });

  it("fires the Continue and View-the-map actions", () => {
    // Arrange
    const onContinue = vi.fn();
    const onViewMap = vi.fn();
    render(<CourseOverview course={makeCourse()} onContinue={onContinue} onViewMap={onViewMap} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /continue learning/i }));
    fireEvent.click(screen.getByRole("button", { name: /view the map/i }));

    // Assert
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onViewMap).toHaveBeenCalledTimes(1);
  });
});
