import { expect, it, vi } from "vitest";
import { createMicrophoneCapture } from "./captureMicrophone";

it("stops a late permission grant after cancellation", async () => {
  let grant!: (stream: MediaStream) => void;
  const permission = new Promise<MediaStream>((resolve) => {
    grant = resolve;
  });
  const stop = vi.fn();
  const close = vi.fn(async () => {});
  const resume = vi.fn(async () => {});
  const getUserMedia = vi.fn(() => permission);
  const capture = createMicrophoneCapture({
    createAudioContext: () => ({ resume, close }) as unknown as AudioContext,
    getUserMedia,
  });
  const starting = capture.start();
  expect(resume.mock.invocationCallOrder[0]).toBeLessThan(
    getUserMedia.mock.invocationCallOrder[0]!,
  );
  capture.cancel();
  expect(close).toHaveBeenCalledOnce();
  grant({ getTracks: () => [{ stop }] } as unknown as MediaStream);
  await expect(starting).rejects.toThrow();
  expect(stop).toHaveBeenCalledOnce();
});

it("does not request permission until explicitly started and reports denial", async () => {
  const close = vi.fn(async () => {});
  const getUserMedia = vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError"));
  const capture = createMicrophoneCapture({
    createAudioContext: () => ({ resume: async () => {}, close }) as unknown as AudioContext,
    getUserMedia,
  });
  expect(getUserMedia).not.toHaveBeenCalled();
  await expect(capture.start()).rejects.toThrow("denied");
  expect(close).toHaveBeenCalledOnce();
  capture.cancel();
});
