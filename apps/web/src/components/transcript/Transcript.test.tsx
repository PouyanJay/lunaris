import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent } from "../../test/fixtures";
import { Transcript } from "./Transcript";

const reasoning = (seq: number, text: string) => makeAgentEvent("reasoning", seq, { text });

describe("Transcript", () => {
  it("shows a waiting affordance before the first agent beat", () => {
    render(<Transcript topic="graphs" events={[]} agentEvents={[]} />);

    expect(screen.getByText(/the agent is starting/i)).toBeInTheDocument();
  });

  it("renders reasoning text and a tool-call card with args + result", () => {
    const agentEvents = [
      makeAgentEvent("reasoning", 0, { text: "Map the prerequisites first." }),
      makeAgentEvent("tool_call", 1, { tool: "extract_concepts", toolArgs: { topic: "graphs" } }),
      makeAgentEvent("tool_result", 2, { tool: "extract_concepts", result: "16 concepts found" }),
    ];

    render(<Transcript topic="graphs" events={[]} agentEvents={agentEvents} />);

    expect(screen.getByText("Map the prerequisites first.")).toBeInTheDocument();
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
    expect(screen.getByText("topic")).toBeInTheDocument();
    expect(screen.getByText("graphs")).toBeInTheDocument();
    expect(screen.getByText("16 concepts found")).toBeInTheDocument();
  });

  it("shows the agent's live plan from the latest todo beat", () => {
    const agentEvents = [
      makeAgentEvent("todo", 0, {
        todos: [
          { content: "Extract concepts", status: "completed" },
          { content: "Design curriculum", status: "in_progress" },
        ],
      }),
    ];

    render(<Transcript topic="graphs" events={[]} agentEvents={agentEvents} />);

    const plan = screen.getByRole("region", { name: /agent plan/i });
    expect(within(plan).getByText("Extract concepts")).toBeInTheDocument();
    expect(within(plan).getByText("Design curriculum")).toBeInTheDocument();
  });

  it("renders the compact stage rail from progress events", () => {
    const events = [makeProgressEvent("graph_built", 1, { kcCount: 5, edgeCount: 4 })];

    render(<Transcript topic="graphs" events={events} agentEvents={[]} />);

    // The rail's live region announces the latest stage label.
    expect(screen.getByRole("status")).toHaveTextContent(/graph_built step/i);
  });

  it("marks an in-flight tool call as running until its result lands", () => {
    const agentEvents = [makeAgentEvent("tool_call", 0, { tool: "verify_claims" })];

    render(<Transcript topic="graphs" events={[]} agentEvents={agentEvents} />);

    expect(screen.getByText("verify_claims")).toBeInTheDocument();
    expect(screen.getByText(/running…/i)).toBeInTheDocument();
  });

  it("follows the feed to the bottom as new events arrive", () => {
    const { rerender } = render(
      <Transcript topic="graphs" events={[]} agentEvents={[reasoning(0, "first")]} />,
    );
    const feed = screen.getByRole("region", { name: /agent transcript/i });
    // jsdom has no layout, so give the feed a scrollable height to observe the effect.
    Object.defineProperty(feed, "scrollHeight", { value: 500, configurable: true });
    feed.scrollTop = 0;

    rerender(
      <Transcript
        topic="graphs"
        events={[]}
        agentEvents={[reasoning(0, "first"), reasoning(1, "second")]}
      />,
    );

    expect(feed.scrollTop).toBe(500);
  });
});
