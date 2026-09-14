import { captureWav } from "./captureWav";

interface Options {
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  onLimit?: () => void;
  createAudioContext?: () => AudioContext;
}
interface Recording {
  stream?: MediaStream;
  context: AudioContext;
  source?: MediaStreamAudioSourceNode;
  worklet?: AudioWorkletNode;
  mute?: GainNode;
  timer?: ReturnType<typeof setTimeout>;
  chunks: Float32Array[];
  samples: number;
  flushed?: () => void;
}

/** Own microphone lifetime, including permission requests that resolve after cancellation. */
export function createMicrophoneCapture(options: Options = {}) {
  let generation = 0;
  let recording: Recording | null = null;
  let starting = false;
  const release = (value: Recording) => {
    clearTimeout(value.timer);
    value.stream?.getTracks().forEach((track) => track.stop());
    value.source?.disconnect();
    value.worklet?.disconnect();
    value.worklet?.port.close();
    value.mute?.disconnect();
    value.flushed?.();
    void value.context.close().catch(() => {});
  };
  const cancel = () => {
    generation++;
    starting = false;
    const previous = recording;
    recording = null;
    if (previous) release(previous);
  };
  const collect = (value: Recording, data: unknown) => {
    if (recording !== value) return;
    if (data === "flushed") {
      value.flushed?.();
      return;
    }
    if (!(data instanceof Float32Array)) return;
    const available = Math.max(0, value.context.sampleRate * 60 - value.samples);
    const chunk = data.slice(0, available);
    value.chunks.push(chunk);
    value.samples += chunk.length;
  };
  const connect = (value: Recording) => {
    const context = value.context;
    value.source = context.createMediaStreamSource(value.stream!);
    value.worklet = new AudioWorkletNode(context, "lunaris-microphone");
    value.mute = context.createGain();
    value.mute.gain.value = 0;
    value.worklet.port.onmessage = (event: MessageEvent<unknown>) => collect(value, event.data);
    value.source.connect(value.worklet).connect(value.mute).connect(context.destination);
    value.timer = setTimeout(() => {
      if (recording === value) {
        value.stream?.getTracks().forEach((track) => track.stop());
        options.onLimit?.();
      }
    }, 60_000);
  };
  const initialize = async (attempt: number) => {
    const getUserMedia =
      options.getUserMedia ?? navigator.mediaDevices?.getUserMedia.bind(navigator.mediaDevices);
    if (!getUserMedia) throw new Error("Microphone recording is unavailable in this browser.");
    const context = options.createAudioContext?.() ?? new AudioContext();
    const value: Recording = { context, chunks: [], samples: 0 };
    recording = value;
    const activation = context.resume();
    void activation.catch(() => {});
    const stream = await getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      video: false,
    });
    if (attempt !== generation) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("Recording cancelled.");
    }
    value.stream = stream;
    await activation;
    await context.audioWorklet.addModule(new URL("./capture.worklet.js", import.meta.url));
    if (recording !== value) throw new Error("Recording cancelled.");
    connect(value);
  };
  return {
    cancel,
    async start() {
      if (starting || recording) throw new Error("Recording already started.");
      starting = true;
      const attempt = ++generation;
      try {
        await initialize(attempt);
      } catch (error) {
        if (attempt === generation) cancel();
        throw error;
      } finally {
        if (attempt === generation) starting = false;
      }
    },
    async finish(): Promise<Blob> {
      const value = recording;
      if (!value?.worklet) throw new Error("No recording is available.");
      clearTimeout(value.timer);
      value.stream?.getTracks().forEach((track) => track.stop());
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(resolve, 250);
        value.flushed = () => {
          clearTimeout(timeout);
          resolve();
        };
        value.worklet!.port.postMessage("flush");
      });
      if (recording !== value) throw new Error("Recording cancelled.");
      recording = null;
      release(value);
      return new Blob([captureWav(value.chunks, value.context.sampleRate)], { type: "audio/wav" });
    },
  };
}
