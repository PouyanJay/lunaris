import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useVoiceCapture } from "./useVoiceCapture";
const recorder = vi.hoisted(() => ({ start: vi.fn(), finish: vi.fn(), cancel: vi.fn() }));
const transcribe = vi.hoisted(() => vi.fn());
vi.mock("../../../lib/voice/captureMicrophone", () => ({
  createMicrophoneCapture: () => recorder,
}));
vi.mock("../../../lib/voice/transcribeVoice", () => ({ transcribeVoice: transcribe }));
const source = { turnSeq: 1, runId: "run-1" };
beforeEach(() => {
  vi.clearAllMocks();
  recorder.start.mockResolvedValue(undefined);
  recorder.finish.mockResolvedValue(new Blob(["clip"]));
});
it("captures explicitly, emits a draft only, and reuses identity on transport retry", async () => {
  const onTranscript = vi.fn();
  transcribe
    .mockRejectedValueOnce(new Error("network"))
    .mockImplementationOnce(async (options) => ({
      text: "Draft",
      source,
      operationId: options.operationId,
      provider: "fixture",
      model: "fixture",
    }));
  const { result } = renderHook(() =>
    useVoiceCapture({ apiBaseUrl: "", sessionId: "s", source, onTranscript }),
  );
  expect(recorder.start).not.toHaveBeenCalled();
  await act(async () => result.current.start());
  expect(result.current.status).toBe("recording");
  await act(async () => result.current.finish());
  expect(result.current.canRetry).toBe(true);
  expect(onTranscript).not.toHaveBeenCalled();
  await act(async () => result.current.retry());
  expect(transcribe.mock.calls[1]![0].operationId).toBe(transcribe.mock.calls[0]![0].operationId);
  expect(transcribe.mock.calls[1]![1]).toBe(transcribe.mock.calls[0]![1]);
  expect(onTranscript).toHaveBeenCalledOnce();
  expect(result.current.status).toBe("idle");
});
it("aborts and ignores a late transcription after moving to another turn", async () => {
  const onTranscript = vi.fn();
  let deliver!: (value: unknown) => void;
  transcribe.mockImplementation(
    () =>
      new Promise((resolve) => {
        deliver = resolve;
      }),
  );
  const { result, rerender } = renderHook(
    ({ source }) => useVoiceCapture({ apiBaseUrl: "", sessionId: "s", source, onTranscript }),
    { initialProps: { source } },
  );
  await act(async () => result.current.start());
  let finishing!: Promise<void>;
  await act(async () => {
    finishing = result.current.finish();
  });
  const signal = transcribe.mock.calls[0]![2] as AbortSignal;
  rerender({ source: { turnSeq: 2, runId: "run-2" } });
  expect(signal.aborted).toBe(true);
  await act(async () => {
    deliver({ text: "Stale" });
    await finishing;
  });
  expect(onTranscript).not.toHaveBeenCalled();
  expect(result.current.status).toBe("idle");
});

it("allows a new recording after an empty or failed capture", async () => {
  recorder.finish.mockRejectedValueOnce(new Error("empty"));
  const { result } = renderHook(() =>
    useVoiceCapture({ apiBaseUrl: "", sessionId: "s", source, onTranscript: vi.fn() }),
  );
  await act(async () => result.current.start());
  await act(async () => result.current.finish());
  expect(result.current.status).toBe("error");
  await act(async () => result.current.start());
  expect(result.current.status).toBe("recording");
  expect(recorder.start).toHaveBeenCalledTimes(2);
});
