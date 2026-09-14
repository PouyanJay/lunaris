import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useVoicePlayback } from "./useVoicePlayback";
import type { VoiceSource } from "../../../lib/voice/types";

afterEach(() => vi.unstubAllGlobals());
it("requests only on a gesture and aborts on source change and unmount", async () => {
  const signals: AbortSignal[] = [];
  const close = vi.fn(async () => {});
  const resume = vi.fn(async () => {});
  vi.stubGlobal(
    "AudioContext",
    class {
      close = close;
      resume = resume;
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          const signal = init.signal!;
          signals.push(signal);
          signal.addEventListener("abort", () => reject(new DOMException("Stopped", "AbortError")));
        }),
    ),
  );
  const source: VoiceSource = { turnSeq: 1, runId: "run-1" };
  const { result, rerender, unmount } = renderHook(
    ({ source }) => useVoicePlayback({ apiBaseUrl: "", sessionId: "session", source }),
    { initialProps: { source } },
  );
  expect(fetch).not.toHaveBeenCalled();
  await act(async () => {
    void result.current.play();
  });
  expect(resume).toHaveBeenCalledTimes(1);
  expect(signals).toHaveLength(1);
  rerender({ source: { turnSeq: 2, runId: "run-2" } });
  expect(signals[0]?.aborted).toBe(true);
  await act(async () => {
    void result.current.play();
  });
  unmount();
  expect(signals[1]?.aborted).toBe(true);
  expect(close).toHaveBeenCalledTimes(2);
});
