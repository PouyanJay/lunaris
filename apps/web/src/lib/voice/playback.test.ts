import { describe, expect, it, vi } from "vitest";
import { createVoicePlayback } from "./playback";

function audio() {
  const nodes: {
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
    onended: (() => void) | null;
    buffer: AudioBuffer | null;
    connect: ReturnType<typeof vi.fn>;
  }[] = [];
  const samples: Float32Array[] = [];
  const context = {
    currentTime: 0,
    destination: {},
    resume: vi.fn(async () => {}),
    close: vi.fn(async () => {}),
    createBuffer: vi.fn((_channels: number, length: number) => ({
      duration: length / 24000,
      copyToChannel: (data: Float32Array) => samples.push(data),
    })),
    createBufferSource: () => {
      const node = {
        start: vi.fn(),
        stop: vi.fn(),
        disconnect: vi.fn(),
        onended: null as (() => void) | null,
        buffer: null as AudioBuffer | null,
        connect: vi.fn(),
      };
      nodes.push(node);
      return node;
    },
  };
  return { context: context as unknown as AudioContext, raw: context, nodes, samples };
}
const source = { turnSeq: 1, runId: "run-1" };
const tick = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve();
};
function setup() {
  const sound = audio();
  let stream!: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const fetcher = vi.fn(
    async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            stream = c;
          },
          cancel,
        }),
        { headers: { "Content-Type": "audio/pcm", "X-Audio-Sample-Rate": "24000" } },
      ),
  );
  const playback = createVoicePlayback({
    apiBaseUrl: "https://api.test",
    sessionId: "session",
    fetcher,
    createAudioContext: () => sound.context,
  });
  return {
    ...sound,
    playback,
    fetcher,
    cancel,
    enqueue: (data: number[]) => stream.enqueue(new Uint8Array(data)),
    end: () => stream.close(),
  };
}
describe("streaming tutor playback", () => {
  it("plays successive chunks before EOF and preserves PCM byte boundaries", async () => {
    const s = setup();
    const done = s.playback.play(source);
    await tick();
    s.enqueue([0, 128, 255]);
    await tick();
    expect(s.samples[0]?.[0]).toBe(-1);
    s.enqueue([127]);
    await tick();
    expect(s.samples[1]?.[0]).toBeCloseTo(32767 / 32768);
    expect(s.nodes).toHaveLength(2);
    s.end();
    await tick();
    s.nodes.forEach((n) => n.onended?.());
    await done;
    expect(s.playback.getSnapshot().status).toBe("idle");
  });
  it("rejects malformed EOF and stops already scheduled audio", async () => {
    const s = setup();
    const done = s.playback.play(source);
    await tick();
    s.enqueue([1, 0, 3]);
    s.end();
    await done;
    expect(s.playback.getSnapshot().status).toBe("error");
    expect(s.nodes[0]?.stop).toHaveBeenCalled();
  });
  it("bounds scheduled audio and aborts backpressure immediately", async () => {
    const s = setup();
    const done = s.playback.play(source);
    await tick();
    s.enqueue(Array(24000 * 10).fill(0));
    await tick();
    expect(s.nodes.length).toBeLessThanOrEqual(4);
    s.playback.stop();
    await done;
    expect(s.nodes.every((n) => n.stop.mock.calls.length === 1)).toBe(true);
    expect(s.raw.close).toHaveBeenCalled();
    expect(s.cancel).toHaveBeenCalled();
  });
  it("does not request audio after a denied user activation", async () => {
    const s = setup();
    s.raw.resume.mockRejectedValue(new Error("denied"));
    await s.playback.play(source);
    expect(s.fetcher).not.toHaveBeenCalled();
    expect(s.playback.getSnapshot().error).toContain("text");
  });
  it("deduplicates concurrent clicks and retains the paid operation ID on retry", async () => {
    const s = setup();
    const first = s.playback.play(source);
    const duplicate = s.playback.play(source);
    await tick();
    expect(s.fetcher).toHaveBeenCalledTimes(1);
    const firstBody = (s.fetcher.mock.calls as unknown as [string, RequestInit][])[0]?.[1].body;
    s.playback.stop();
    await Promise.all([first, duplicate]);
    const retry = s.playback.play(source);
    await tick();
    expect((s.fetcher.mock.calls as unknown as [string, RequestInit][])[1]?.[1].body).toBe(
      firstBody,
    );
    expect(JSON.parse(String(firstBody))).toMatchObject({ source });
    expect(JSON.parse(String(firstBody))).not.toHaveProperty("text");
    s.playback.stop();
    await retry;
  });
});

it("ignores a late response after stop and never schedules obsolete speech", async () => {
  const sound = audio();
  let resolve!: (response: Response) => void;
  const fetcher = vi.fn(
    () =>
      new Promise<Response>((r) => {
        resolve = r;
      }),
  );
  const playback = createVoicePlayback({
    apiBaseUrl: "",
    sessionId: "session",
    fetcher,
    createAudioContext: () => sound.context,
  });
  const done = playback.play(source);
  await tick();
  playback.stop();
  const cancel = vi.fn();
  resolve(
    new Response(new ReadableStream({ cancel }), {
      headers: { "Content-Type": "audio/pcm", "X-Audio-Sample-Rate": "24000" },
    }),
  );
  await done;
  expect(sound.nodes).toHaveLength(0);
  expect(cancel).toHaveBeenCalled();
  expect(playback.getSnapshot().status).toBe("idle");
});
it.each(["audio/wav", "text/html"])(
  "rejects unexpected response %s without playing it",
  async (type) => {
    const sound = audio();
    const playback = createVoicePlayback({
      apiBaseUrl: "",
      sessionId: "s",
      createAudioContext: () => sound.context,
      fetcher: async () =>
        new Response(new Uint8Array([1, 2]), { headers: { "Content-Type": type } }),
    });
    await playback.play(source);
    expect(sound.nodes).toHaveLength(0);
    expect(playback.getSnapshot().status).toBe("error");
  },
);

it("times out a stalled audio stream and leaves text available", async () => {
  vi.useFakeTimers();
  try {
    const s = setup();
    const done = s.playback.play(source);
    await tick();
    await vi.advanceTimersByTimeAsync(30_000);
    await done;
    expect(s.cancel).toHaveBeenCalled();
    expect(s.playback.getSnapshot()).toMatchObject({
      status: "error",
      error: expect.stringContaining("text"),
    });
  } finally {
    vi.useRealTimers();
  }
});

it.each(["backpressure", "final drain"])(
  "times out interrupted playback during %s and releases resources",
  async (phase) => {
    vi.useFakeTimers();
    try {
      const s = setup();
      const done = s.playback.play(source);
      await tick();
      s.enqueue(Array(phase === "backpressure" ? 12000 * 2 * 5 : 2).fill(0));
      if (phase === "final drain") s.end();
      await tick();
      expect(s.playback.getSnapshot().status).toBe("playing");
      await vi.advanceTimersByTimeAsync(30_000);
      expect(s.playback.getSnapshot().status).toBe("error");
      await done;
      expect(s.nodes.every((node) => node.stop.mock.calls.length === 1)).toBe(true);
      expect(s.raw.close).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  },
);
