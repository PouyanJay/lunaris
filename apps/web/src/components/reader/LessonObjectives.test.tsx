import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LessonObjectives } from "./LessonObjectives";
import type { Objective } from "../../types/course";

const OBJECTIVES: Objective[] = [
  {
    statement: "Explain HTTPS as HTTP over TLS.",
    bloomLevel: "understand",
    kc: "kc-1",
    assessedBy: [],
  },
  { statement: "Sequence the TLS handshake.", bloomLevel: "analyze", kc: "kc-2", assessedBy: [] },
  {
    statement: "Define certificate authorities.",
    bloomLevel: "remember",
    kc: "kc-3",
    assessedBy: [],
  },
];

describe("LessonObjectives", () => {
  it("lists each objective with its Bloom level", () => {
    render(<LessonObjectives objectives={OBJECTIVES} />);
    expect(screen.getByText("Explain HTTPS as HTTP over TLS.")).toBeInTheDocument();
    expect(screen.getByText("analyze")).toBeInTheDocument();
  });

  it("counts understanding when progress is provided", () => {
    render(<LessonObjectives objectives={OBJECTIVES} understoodIndexes={new Set([0, 2])} />);
    expect(screen.getByText("2 of 3 understood")).toBeInTheDocument();
  });

  it("shows no counter without progress data", () => {
    render(<LessonObjectives objectives={OBJECTIVES} />);
    expect(screen.queryByText(/understood/)).not.toBeInTheDocument();
  });

  it("offers a toggle per objective that reports the next understood state", () => {
    const onToggle = vi.fn();
    render(
      <LessonObjectives
        objectives={OBJECTIVES}
        understoodIndexes={new Set([1])}
        onToggleObjective={onToggle}
      />,
    );

    const toggles = screen.getAllByRole("button", { name: /understood/i });
    expect(toggles).toHaveLength(3);
    expect(toggles[1]).toHaveAttribute("aria-pressed", "true");
    expect(toggles[0]).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(toggles[0]!);
    expect(onToggle).toHaveBeenCalledWith(0, true);
    fireEvent.click(toggles[1]!);
    expect(onToggle).toHaveBeenCalledWith(1, false);
  });

  it("renders no toggles without a handler (offline)", () => {
    render(<LessonObjectives objectives={OBJECTIVES} understoodIndexes={new Set()} />);
    expect(screen.queryByRole("button", { name: /understood/i })).not.toBeInTheDocument();
  });
});
