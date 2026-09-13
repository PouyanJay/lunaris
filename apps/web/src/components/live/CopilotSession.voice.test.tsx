import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode, ComponentType } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { VoiceTranscript } from "../../lib/voice/types";
import { CopilotSession } from "./CopilotSession";
const send = vi.hoisted(() => vi.fn());
vi.mock("../../hooks/useAuth", () => ({ useAuth: () => ({ session: null }) }));
vi.mock("@copilotkit/react-core", () => ({
  CopilotKit: ({ children }: { children: ReactNode }) => <>{children}</>,
  useCoAgent: () => ({ state: { status: "active" } }),
  useRenderToolCall: () => {},
}));
vi.mock("@copilotkit/react-ui", () => ({
  CopilotChat: ({
    Input,
  }: {
    Input: ComponentType<{
      onSend: (text: string) => void;
      inProgress: boolean;
      chatReady: boolean;
    }>;
  }) => <Input onSend={send} inProgress={false} chatReady />,
}));
vi.mock("./voice/VoiceSessionControls", () => ({
  VoiceSessionControls: ({
    onTranscript,
    canAnswer,
  }: {
    onTranscript: (draft: VoiceTranscript) => void;
    canAnswer: boolean;
  }) => (
    <button
      disabled={!canAnswer}
      onClick={() =>
        onTranscript({
          text: "Reviewed speech",
          source: { turnSeq: 1, runId: "r" },
          operationId: "recording",
          provider: "fixture",
          model: "fixture",
        })
      }
    >
      Complete recording
    </button>
  ),
}));
it("edits the existing Copilot composer and submits through its original send path", async () => {
  render(
    <CopilotSession
      runtimeUrl="http://runtime.test"
      sessionId="s"
      topic="Fractions"
      standingTurn="Try this"
      standingSeq={1}
      voice={{
        apiBaseUrl: "",
        answerSource: { turnSeq: 1, runId: "r" },
        speechSource: { turnSeq: 1, runId: "r" },
        speechKind: "tutor",
        canAnswer: true,
      }}
    />,
  );
  const record = screen.getByRole("button", { name: "Complete recording" });
  await waitFor(() => expect(record).toBeEnabled());
  fireEvent.click(record);
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  expect(screen.getByRole("textbox")).toHaveValue("Reviewed speech");
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(send).toHaveBeenCalledOnce();
  expect(send).toHaveBeenCalledWith("Reviewed speech");
});

beforeEach(() => send.mockClear());
it.each(["session", "turn", "api"])("discards delivered speech on %s changes", async (change) => {
  const panel = (changed: boolean) => (
    <CopilotSession
      runtimeUrl="http://runtime.test"
      sessionId={changed && change === "session" ? "other" : "s"}
      topic="Fractions"
      standingTurn="Try this"
      standingSeq={changed && change === "turn" ? 2 : 1}
      voice={{
        apiBaseUrl: changed && change === "api" ? "https://other.test" : "",
        answerSource: { turnSeq: changed && change === "turn" ? 2 : 1, runId: "r" },
        speechSource: { turnSeq: 1, runId: "r" },
        canAnswer: true,
      }}
    />
  );
  const view = render(panel(false));
  const record = screen.getByRole("button", { name: "Complete recording" });
  await waitFor(() => expect(record).toBeEnabled());
  fireEvent.click(record);
  expect(screen.getByRole("textbox")).toHaveValue("Reviewed speech");
  view.rerender(panel(true));
  expect(screen.getByRole("textbox")).toHaveValue("");
  expect(send).not.toHaveBeenCalled();
});
