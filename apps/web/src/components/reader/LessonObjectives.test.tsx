import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
