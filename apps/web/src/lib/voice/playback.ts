import { authedFetch } from "../apiClient";
import type { VoiceSource } from "./types";
import { createPcmDecoder } from "./playbackPcm";

export interface PlaybackSnapshot {
  status: "idle" | "loading" | "playing" | "error";
  error: string | null;
}
interface Options {
  apiBaseUrl: string;
  sessionId: string;
  fetcher?: typeof fetch;
  createAudioContext?: () => AudioContext;
}
interface Attempt {
  abort: AbortController;
  context: AudioContext;
  nodes: Set<AudioBufferSourceNode>;
  wake: Set<() => void>;
  reader?: ReadableStreamDefaultReader<Uint8Array>;
  nextTime: number;
  timeout?: ReturnType<typeof setTimeout>;
}
const SAMPLE_RATE = 24000;
const MAX_SCHEDULED_BLOCKS = 4;
const FALLBACK = "Audio is unavailable. Continue with the tutor’s text.";

/** Explicit playback only. Replay retains the operation ID so transport retries cannot rebill. */
export function createVoicePlayback(options: Options) {
  let snapshot: PlaybackSnapshot = { status: "idle", error: null };
  const listeners = new Set<() => void>();
  let active: Attempt | null = null;
  let currentKey = "";
  let operationId = "";
  let pending: Promise<void> | null = null;
  const emit = (status: PlaybackSnapshot["status"], error: string | null = null) => {
    snapshot = { status, error };
    listeners.forEach((listener) => listener());
  };
  const release = (attempt: Attempt) => {
    clearTimeout(attempt.timeout);
    attempt.abort.abort();
    void attempt.reader?.cancel().catch(() => {});
    attempt.nodes.forEach((node) => {
      node.onended = null;
      node.stop();
      node.disconnect();
    });
    attempt.nodes.clear();
    attempt.wake.forEach((wake) => wake());
    attempt.wake.clear();
    void attempt.context.close().catch(() => {});
  };
  const armDeadline = (attempt: Attempt) => {
    clearTimeout(attempt.timeout);
    attempt.timeout = setTimeout(() => {
      if (active !== attempt) return;
      active = null;
      release(attempt);
      emit("error", FALLBACK);
    }, 30_000);
  };
  const stop = () => {
    const previous = active;
    active = null;
    pending = null;
    if (previous) release(previous);
    emit("idle");
  };
  const waitForEnd = (attempt: Attempt) => {
    armDeadline(attempt);
    return new Promise<void>((resolve) => attempt.wake.add(resolve));
  };
  const schedule = async (attempt: Attempt, samples: Float32Array<ArrayBuffer>) => {
    while (attempt.nodes.size >= MAX_SCHEDULED_BLOCKS && active === attempt)
      await waitForEnd(attempt);
    if (active !== attempt) return;
    const buffer = attempt.context.createBuffer(1, samples.length, SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const node = attempt.context.createBufferSource();
    node.buffer = buffer;
    node.connect(attempt.context.destination);
    node.onended = () => {
      node.disconnect();
      attempt.nodes.delete(node);
      attempt.wake.forEach((wake) => wake());
      attempt.wake.clear();
    };
    attempt.nodes.add(node);
    const start = Math.max(attempt.context.currentTime, attempt.nextTime);
    node.start(start);
    attempt.nextTime = start + buffer.duration;
    emit("playing");
  };
  const requestAudio = async (attempt: Attempt, source: VoiceSource, id: string) => {
    const response = await (options.fetcher ?? authedFetch)(
      `${options.apiBaseUrl}/api/live/sessions/${encodeURIComponent(options.sessionId)}/voice/speech`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, operationId: id }),
        signal: attempt.abort.signal,
      },
    );
    if (active !== attempt) {
      await response.body?.cancel();
      return;
    }
    if (
      !response.ok ||
      response.headers.get("Content-Type")?.split(";")[0]?.trim() !== "audio/pcm" ||
      (response.headers.has("X-Audio-Sample-Rate") &&
        response.headers.get("X-Audio-Sample-Rate") !== String(SAMPLE_RATE)) ||
      !response.body
    ) {
      await response.body?.cancel();
      throw new Error("Invalid audio response");
    }
    return response.body.getReader();
  };
  const receiveAudio = async (attempt: Attempt) => {
    const decoder = createPcmDecoder();
    while (active === attempt) {
      armDeadline(attempt);
      const { value, done } = await attempt.reader!.read();
      clearTimeout(attempt.timeout);
      if (active !== attempt) return;
      if (done) break;
      for (const samples of decoder.decode(value)) {
        if (active !== attempt) return;
        await schedule(attempt, samples);
      }
    }
    if (active !== attempt) return;
    decoder.finish();
    while (attempt.nodes.size && active === attempt) await waitForEnd(attempt);
  };
  const stream = async (attempt: Attempt, source: VoiceSource, id: string) => {
    try {
      // Called synchronously from play, before the first network await, to preserve activation.
      await attempt.context.resume();
      if (active !== attempt) return;
      const reader = await requestAudio(attempt, source, id);
      if (!reader) return;
      attempt.reader = reader;
      await receiveAudio(attempt);
      if (active === attempt) {
        active = null;
        release(attempt);
        emit("idle");
      }
    } catch {
      if (active === attempt) {
        active = null;
        release(attempt);
        emit("error", FALLBACK);
      }
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    stop,
    play(source: VoiceSource): Promise<void> {
      const key = JSON.stringify([source.turnSeq, source.runId, source.exchangeSequence ?? null]);
      if (active && key === currentKey && pending) return pending;
      stop();
      if (key !== currentKey) {
        currentKey = key;
        operationId = crypto.randomUUID();
      }
      try {
        const context =
          options.createAudioContext?.() ?? new AudioContext({ sampleRate: SAMPLE_RATE });
        const attempt: Attempt = {
          abort: new AbortController(),
          context,
          nodes: new Set(),
          wake: new Set(),
          nextTime: 0,
        };
        active = attempt;
        armDeadline(attempt);
        emit("loading");
        pending = stream(attempt, source, operationId);
        return pending;
      } catch {
        emit("error", FALLBACK);
        return Promise.resolve();
      }
    },
  };
}
