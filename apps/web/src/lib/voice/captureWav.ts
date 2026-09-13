/** Encode a bounded microphone clip as the server's mono 16kHz PCM16 WAV contract. */
export function captureWav(chunks: readonly Float32Array[], sampleRate: number): ArrayBuffer {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  if (
    !Number.isFinite(sampleRate) ||
    sampleRate < 16000 ||
    sampleRate > 192000 ||
    !length ||
    length > sampleRate * 60
  )
    throw new Error("Recording must contain up to 60 seconds of audio.");
  const input = joinSamples(chunks, length);
  const ratio = sampleRate / 16000;
  const count = Math.floor(length / ratio);
  if (!count) throw new Error("Recording is empty.");
  const view = wavHeader(count);
  writeSamples(view, input, ratio);
  return view.buffer as ArrayBuffer;
}

function joinSamples(chunks: readonly Float32Array[], length: number): Float32Array {
  const input = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    if (chunk.some((sample) => !Number.isFinite(sample)))
      throw new Error("Invalid microphone samples.");
    input.set(chunk, offset);
    offset += chunk.length;
  }
  return input;
}

function wavHeader(count: number): DataView {
  const output = new ArrayBuffer(44 + count * 2);
  const view = new DataView(output);
  const label = (at: number, text: string) => {
    for (let index = 0; index < text.length; index++)
      view.setUint8(at + index, text.charCodeAt(index));
  };
  label(0, "RIFF");
  view.setUint32(4, 36 + count * 2, true);
  label(8, "WAVE");
  label(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  label(36, "data");
  view.setUint32(40, count * 2, true);
  return view;
}

function writeSamples(view: DataView, input: Float32Array, ratio: number) {
  const count = (view.byteLength - 44) / 2;
  for (let index = 0; index < count; index++) {
    const start = index * ratio;
    const end = (index + 1) * ratio;
    let sum = 0;
    for (let position = Math.floor(start); position < Math.ceil(end); position++) {
      const weight = Math.min(end, position + 1) - Math.max(start, position);
      sum += (input[position] ?? 0) * weight;
    }
    const sample = Math.max(-1, Math.min(1, sum / ratio));
    view.setInt16(44 + index * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
}
