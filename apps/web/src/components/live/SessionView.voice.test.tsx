import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { VoiceTranscript } from "../../lib/voice/types";
import { SessionView } from "./SessionView";
const answer = vi.hoisted(() => vi.fn());
const source = vi.hoisted(() => ({ sessionId: "s", seq: 1 }));
vi.mock("../../hooks/useLiveSession", () => ({
  useLiveSession: () => ({
    state: {
      status: "ready",
      session: {
        sessionId: source.sessionId,
        graphId: "g",
        status: "active",
        startedAt: "2026-09-13T00:00:00Z",
        turns: [
          {
            seq: source.seq,
            runId: "r",
            tutor: "Try this",
            move: { kind: "introduce", nodeId: "n", reason: "start" },
            answer: null,
            grade: null,
            criterion: { kind: "explain", statement: "Explain this" },
          },
        ],
      },
    },
    answer,
    retry: vi.fn(),
    refresh: vi.fn(),
  }),
}));
vi.mock("./voice/VoiceSessionControls", () => ({
  VoiceSessionControls: ({
    onTranscript,
    answerSource,
  }: {
    onTranscript: (draft: VoiceTranscript) => void;
    answerSource: VoiceTranscript["source"];
  }) => (
    <button
      onClick={() =>
        onTranscript({
          text: "Reviewed spoken answer",
          source: answerSource,
          operationId: "recording",
          provider: "fixture",
          model: "fixture",
        })
      }
      data-source={JSON.stringify(answerSource)}
    >
      Complete recording
    </button>
  ),
}));
it("puts speech in the existing REST composer and submits only on confirmation", () => {
  render(<SessionView apiBaseUrl="" graphId="g" topic="Fractions" />);
  const record = screen.getByRole("button", { name: "Complete recording" });
  expect(record).toHaveAttribute("data-source", JSON.stringify({ turnSeq: 1, runId: "r" }));
  fireEvent.click(record);
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  expect(screen.getByRole("textbox")).toHaveValue("Reviewed spoken answer");
  expect(answer).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(answer).toHaveBeenCalledOnce();
  expect(answer).toHaveBeenCalledWith("Reviewed spoken answer");
});

beforeEach(() => {
  answer.mockClear();
  source.sessionId = "s";
  source.seq = 1;
});
it.each(["session", "turn", "api"])("discards delivered speech on %s changes", (change) => {
  const view = render(<SessionView apiBaseUrl="" graphId="g" topic="Fractions" />);
  fireEvent.click(screen.getByRole("button", { name: "Complete recording" }));
  expect(screen.getByRole("textbox")).toHaveValue("Reviewed spoken answer");
  if (change === "session") source.sessionId = "other";
  if (change === "turn") source.seq = 2;
  view.rerender(
    <SessionView
      apiBaseUrl={change === "api" ? "https://other.test" : ""}
      graphId="g"
      topic="Fractions"
    />,
  );
  expect(screen.getByRole("textbox")).toHaveValue("");
  expect(answer).not.toHaveBeenCalled();
});
