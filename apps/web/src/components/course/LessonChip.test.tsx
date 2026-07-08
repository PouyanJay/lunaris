import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LessonChip } from "./LessonChip";

describe("LessonChip", () => {
  it("shows the lesson number for an unfinished lesson", () => {
    const { container } = render(<LessonChip number={3} state="up_next" />);
    const chip = container.firstElementChild!;
    expect(chip).toHaveTextContent("3");
    expect(chip).toHaveAttribute("data-state", "up_next");
  });

  it("shows the done glyph instead of the number once a lesson is done", () => {
    const { container } = render(<LessonChip number={3} state="done" />);
    expect(container.firstElementChild).toHaveTextContent("✓");
  });

  it("is decorative — the owning row carries the accessible state", () => {
    const { container } = render(<LessonChip number={1} state="in_progress" />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("supports the rail's compact size", () => {
    const { container } = render(<LessonChip number={1} state="up_next" size="sm" />);
    expect(container.firstElementChild!.className).toMatch(/sm/);
  });
});
