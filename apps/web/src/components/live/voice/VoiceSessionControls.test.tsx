import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { VoiceTranscript } from "../../../lib/voice/types";
import { VoiceSessionControls } from "./VoiceSessionControls";

const mocks = vi.hoisted(() => ({
  capture: {
    status: "idle",
    error: null as string | null,
    canRetry: false,
    start: vi.fn(),
    finish: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
  },
  playback: { status: "idle", error: null as string | null, play: vi.fn(), stop: vi.fn() },
  receive: undefined as ((draft: VoiceTranscript) => void) | undefined,
}));
vi.mock("./useVoiceCapture", () => ({
  useVoiceCapture: ({ onTranscript }: { onTranscript: typeof mocks.receive }) => {
    mocks.receive = onTranscript;
    return mocks.capture;
  },
}));
vi.mock("./useVoicePlayback", () => ({ useVoicePlayback: () => mocks.playback }));
const source = { turnSeq: 1, runId: "turn-1" };
const draft = {
  text: "My recorded answer",
  source,
  operationId: "draft-1",
  provider: "elevenlabs",
  model: "scribe_v2",
};
const props = {
  apiBaseUrl: "",
  sessionId: "session",
  answerSource: source,
  speechSource: source,
  canAnswer: true,
  busy: false,
  onAnswer: vi.fn(),
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.capture.status = "idle";
  mocks.capture.error = null;
  mocks.capture.canRetry = false;
  mocks.playback.status = "idle";
});
it("stops speech before explicit microphone activation and never starts automatically", () => {
  render(<VoiceSessionControls {...props} />);
  expect(mocks.capture.start).not.toHaveBeenCalled();
  expect(mocks.playback.play).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Speak" }));
  expect(mocks.playback.stop.mock.invocationCallOrder.at(-1)).toBeLessThan(
    mocks.capture.start.mock.invocationCallOrder[0]!,
  );
});
it("requires editable draft confirmation and sends only once", () => {
  render(<VoiceSessionControls {...props} />);
  act(() => mocks.receive?.(draft));
  expect(props.onAnswer).not.toHaveBeenCalled();
  const input = screen.getByRole("textbox", { name: "Your answer" });
  fireEvent.change(input, { target: { value: "Edited explanation" } });
  fireEvent.submit(input.closest("form")!);
  act(() => mocks.receive?.(draft));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(props.onAnswer).toHaveBeenCalledOnce();
  expect(props.onAnswer).toHaveBeenCalledWith("Edited explanation");
});
it("discards drafts and cancels capture when the answer source changes or becomes busy", () => {
  const view = render(<VoiceSessionControls {...props} />);
  const oldReceive = mocks.receive;
  act(() => mocks.receive?.(draft));
  view.rerender(<VoiceSessionControls {...props} answerSource={{ turnSeq: 2, runId: "turn-2" }} />);
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  act(() => oldReceive?.(draft));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  view.rerender(<VoiceSessionControls {...props} busy />);
  act(() => mocks.receive?.(draft));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Speak" })).toBeDisabled();
  expect(mocks.capture.cancel).toHaveBeenCalled();
});
it("keeps closed-session speech available without a microphone action", () => {
  render(<VoiceSessionControls {...props} canAnswer={false} answerSource={null} />);
  expect(screen.queryByRole("button", { name: "Speak" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Read aloud" }));
  expect(mocks.playback.play).toHaveBeenCalledOnce();
});
it("offers cancel during recording and recovery alongside text fallback", () => {
  mocks.capture.status = "recording";
  const view = render(<VoiceSessionControls {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Finish recording" }));
  expect(mocks.capture.finish).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Cancel recording" }));
  expect(mocks.capture.cancel).toHaveBeenCalled();
  mocks.capture.status = "error";
  mocks.capture.error = "Microphone access is unavailable.";
  mocks.capture.canRetry = true;
  view.rerender(<VoiceSessionControls {...props} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Microphone access");
  expect(screen.getByText(/You can still type/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Retry transcription" }));
  expect(mocks.capture.retry).toHaveBeenCalledOnce();
});
it("stops only local voice work when hidden or unmounted", () => {
  const view = render(<VoiceSessionControls {...props} />);
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
  fireEvent(document, new Event("visibilitychange"));
  expect(mocks.capture.cancel).toHaveBeenCalled();
  expect(mocks.playback.stop).toHaveBeenCalled();
  expect(props.onAnswer).not.toHaveBeenCalled();
  view.unmount();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

it.each(["requesting", "transcribing"])("allows cancelling %s without submitting", (status) => {
  mocks.capture.status = status;
  render(<VoiceSessionControls {...props} />);
  expect(screen.getByRole("button", { name: "Speak" })).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", {
      name: status === "transcribing" ? "Cancel transcription" : "Cancel recording",
    }),
  );
  expect(mocks.capture.cancel).toHaveBeenCalled();
  expect(props.onAnswer).not.toHaveBeenCalled();
});
it("reads simulator reactions explicitly and offers a local audio stop", () => {
  const view = render(<VoiceSessionControls {...props} speechKind="simulator" />);
  fireEvent.click(screen.getByRole("button", { name: "Read reaction" }));
  expect(mocks.playback.play).toHaveBeenCalledOnce();
  mocks.playback.status = "playing";
  view.rerender(<VoiceSessionControls {...props} speechKind="simulator" />);
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  expect(mocks.playback.stop).toHaveBeenCalled();
  expect(props.onAnswer).not.toHaveBeenCalled();
});
it("delivers a transcript to the existing composer without another answer form or submission", () => {
  const onTranscript = vi.fn();
  render(<VoiceSessionControls {...props} onTranscript={onTranscript} />);
  act(() => mocks.receive?.(draft));
  expect(onTranscript).toHaveBeenCalledOnce();
  expect(onTranscript).toHaveBeenCalledWith(draft);
  expect(props.onAnswer).not.toHaveBeenCalled();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByText("Your transcript is ready. Review it before sending.")).toBeVisible();
  act(() => mocks.receive?.(draft));
  expect(onTranscript).toHaveBeenCalledOnce();
});
it.each(["source", "busy"])(
  "clears the composer delivery notification after a %s change",
  (change) => {
    const onTranscript = vi.fn();
    const view = render(<VoiceSessionControls {...props} onTranscript={onTranscript} />);
    act(() => mocks.receive?.(draft));
    view.rerender(
      <VoiceSessionControls
        {...props}
        onTranscript={onTranscript}
        busy={change === "busy"}
        answerSource={change === "source" ? { turnSeq: 2, runId: "turn-2" } : source}
      />,
    );
    expect(
      screen.queryByText("Your transcript is ready. Review it before sending."),
    ).not.toBeInTheDocument();
    expect(props.onAnswer).not.toHaveBeenCalled();
  },
);
it.each([true, false])(
  "hides unavailable voice controls while preserving cleanup (canAnswer=%s)",
  (canAnswer) => {
    const view = render(<VoiceSessionControls {...props} />);
    mocks.capture.cancel.mockClear();
    mocks.playback.stop.mockClear();
    view.rerender(
      <VoiceSessionControls
        {...props}
        answerSource={null}
        speechSource={null}
        canAnswer={canAnswer}
      />,
    );
    expect(screen.queryByRole("region", { name: "Voice controls" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(mocks.capture.cancel).toHaveBeenCalled();
    expect(mocks.playback.stop).toHaveBeenCalled();
  },
);
it("does not announce an empty idle status", () => {
  render(<VoiceSessionControls {...props} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Speak" })).toBeVisible();
});
