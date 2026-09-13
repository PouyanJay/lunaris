const BLOCK_SAMPLES = 12000;
const MAX_BYTES = 24000 * 2 * 180;

/** Decode bounded PCM16 little-endian chunks, carrying an odd byte across network reads. */
export function createPcmDecoder() {
  let trailing: number | undefined;
  let received = 0;
  function* decode(value: Uint8Array): Generator<Float32Array<ArrayBuffer>> {
    received += value.byteLength;
    if (received > MAX_BYTES) throw new Error("Audio too long");
    let offset = 0;
    while (offset < value.length) {
      const available = Math.floor((value.length - offset + (trailing === undefined ? 0 : 1)) / 2);
      if (!available) {
        trailing = value[offset++];
        break;
      }
      const count = Math.min(available, BLOCK_SAMPLES);
      const samples = new Float32Array(count);
      for (let index = 0; index < count; index++) {
        const low = trailing ?? value[offset++]!;
        trailing = undefined;
        const raw = low | (value[offset++]! << 8);
        samples[index] = (raw >= 32768 ? raw - 65536 : raw) / 32768;
      }
      yield samples;
    }
  }
  return {
    decode,
    finish() {
      if (trailing !== undefined || received === 0) throw new Error("Incomplete audio");
    },
  };
}
