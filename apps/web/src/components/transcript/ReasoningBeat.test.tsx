import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReasoningBeat } from "./ReasoningBeat";

describe("ReasoningBeat", () => {
  it("renders plain prose with a caret while streaming", () => {
    render(<ReasoningBeat text="Ordering the prerequisites." streaming />);

    expect(screen.getByText("Ordering the prerequisites.")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-caret")).toBeInTheDocument();
  });

  it("omits the caret when not streaming", () => {
    render(<ReasoningBeat text="Ordering the prerequisites." streaming={false} />);

    expect(screen.queryByTestId("reasoning-caret")).not.toBeInTheDocument();
  });

  it("lifts an embedded JSON blob into a bounded artifact instead of dumping it in the prose", () => {
    const blob = '{"modules":[{"title":"Networking"},{"title":"Crypto"},{"title":"Trust"}]}';
    render(<ReasoningBeat text={`Now designing the curriculum. ${blob}`} streaming={false} />);

    // The prose shows; the JSON is summarised in an artifact (collapsed), not dumped raw alongside.
    expect(screen.getByText("Now designing the curriculum.")).toBeInTheDocument();
    expect(screen.getByText("object · 1 key")).toBeInTheDocument();
    expect(screen.queryByText(/modules/)).not.toBeInTheDocument();
  });

  it("keeps the caret off a trailing streaming JSON blob (the artifact shows its own state)", () => {
    render(<ReasoningBeat text='Designing it: {"modules":[{"title":"Net' streaming />);

    // The last segment is a streaming artifact, so no caret trails it.
    expect(screen.getByText("streaming…")).toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-caret")).not.toBeInTheDocument();
  });
});
