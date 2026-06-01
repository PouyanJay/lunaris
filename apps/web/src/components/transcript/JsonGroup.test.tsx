import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsonGroup } from "./JsonGroup";

describe("JsonGroup", () => {
  it("summarises a uniform run with a true/false tally on the shared boolean key", () => {
    const sources = [
      '{"is_prereq": true, "strength": 0.85}',
      '{"is_prereq": false, "strength": 0.15}',
      '{"is_prereq": true, "strength": 0.72}',
    ];
    render(<JsonGroup sources={sources} closed />);

    // One artifact, not three cards — with a deterministic tally (no model call).
    expect(screen.getByText("3 × is_prereq — 2 true, 1 false")).toBeInTheDocument();
    // Collapsed by default: the raw blobs aren't shown until expanded.
    expect(screen.queryByText(/0\.85/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/0\.85/)).toBeInTheDocument();
  });

  it("falls back to a count when the blobs share no boolean key", () => {
    render(<JsonGroup sources={['{"a": 1}', '{"b": 2}']} closed />);

    expect(screen.getByText("2 snippets")).toBeInTheDocument();
  });

  it("notes a still-streaming run in its summary", () => {
    render(<JsonGroup sources={['{"a": 1}', '{"b": 2}']} closed={false} />);

    expect(screen.getByText("2 snippets · streaming…")).toBeInTheDocument();
  });

  it("caps the expanded preview and notes how many more there are", () => {
    const sources = Array.from({ length: 80 }, (_, i) => `{"n": ${i}}`);
    render(<JsonGroup sources={sources} closed />);

    fireEvent.click(screen.getByRole("button"));
    // Capped at 50 rows, with a note for the remaining 30.
    expect(screen.getByText("…and 30 more")).toBeInTheDocument();
  });
});
